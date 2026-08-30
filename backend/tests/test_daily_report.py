"""Daily report API 测试（multipart 上传 + 4 步流水线）。"""
# pyright: reportCallIssue=false

import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.resource import Resource, ResourceCategory
from src.models.resource_usage import TaskResourceUsage
from src.models.task import Task

# 默认项目 id
PID = 1
USAGE_DATE = "2026-06-28"


def _build_csv_bytes(
    include_labor: bool = True, include_machinery: bool = True
) -> bytes:
    """动态构造施工日报 CSV bytes。

    合法格式要求（参考 src/utils/daily_report_parser.py）：
    - labor 部分：必须包含 "现场人员" 行 + "人员数量" 行（成对）
    - machinery 部分：必须包含 "施工机械" 行 + "数量" 行 + "机械型号" 行（成三）
    """
    lines: list[str] = ["section,col1,col2"]
    if include_labor:
        lines.append("现场人员,dr-r1,dr-r2")
        lines.append("人员数量,5,3")
    if include_machinery:
        lines.append("施工机械,dr-r3,")
        lines.append("数量,2,")
        lines.append("机械型号,PC200,")
    body = "\n".join(lines) + "\n"
    # 加 BOM 让 polars 当作 UTF-8 处理（保险起见）
    return body.encode("utf-8-sig")


@pytest.fixture
def daily_report_csv() -> bytes:
    """合法 CSV（含 labor + machinery）"""
    return _build_csv_bytes(include_labor=True, include_machinery=True)


@pytest.fixture
def empty_csv() -> bytes:
    """不含任何 labor/machinery 标记的 CSV（但格式合法）"""
    return _build_csv_bytes(include_labor=False, include_machinery=False)


@pytest.fixture
def invalid_csv() -> bytes:
    """损坏内容（纯文本但格式合法）"""
    return b"not a valid xlsx file content"


@pytest_asyncio.fixture
async def tasks_for_report(db_session: AsyncSession):
    """插入 2 个 Task（project_id=1）"""
    objs = [
        Task(
            id=20001,
            project_id=PID,
            code="DR-T1",
            name="DR-T1",
            duration=5.0,
            completed=0.0,
        ),
        Task(
            id=20002,
            project_id=PID,
            code="DR-T2",
            name="DR-T2",
            duration=5.0,
            completed=0.0,
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


@pytest_asyncio.fixture
async def resources_for_report(db_session: AsyncSession):
    """插入 1 个 Resource（name="dr-r1"，与 CSV 中的"现场人员 dr-r1"对应）"""
    objs = [
        Resource(
            id=20001,
            project_id=PID,
            name="dr-r1",
            description="d1",
            category=ResourceCategory.labor,
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


def _url(pid: int = PID) -> str:
    return f"/projects/{pid}/daily-report"


async def _parse_batch(
    client: AsyncClient, csv_bytes: bytes, pid: int = PID, filename: str = "test.csv"
) -> str:
    """辅助：调用 /parse，返回 batchId 字符串"""
    resp = await client.post(
        _url(pid) + "/parse",
        files={"file": (filename, csv_bytes, "text/csv")},
        data={"usage_date": USAGE_DATE},
    )
    assert resp.status_code == 200, f"parse failed: {resp.text}"
    return resp.json()["batchId"]


# =============================================================================
# parse 端点
# =============================================================================


@pytest.mark.parametrize(
    "content_factory, code",
    [
        pytest.param(lambda: _build_csv_bytes(), 200, id="valid_csv"),
        pytest.param(lambda: _build_csv_bytes(False, False), 200, id="empty_csv"),
        pytest.param(lambda: b"plain text content", 400, id="txt_format"),
        pytest.param(lambda: b"\x00\x01\x02not an xlsx", 400, id="corrupt_content"),
    ],
)
async def test_parse_daily_report(content_factory, code: int, client: AsyncClient):
    csv_bytes = content_factory()
    # txt/corrupt 用 .txt 后缀，valid/empty 用 .csv
    filename = "test.csv"
    if code == 400:
        filename = "test.txt"
    resp = await client.post(
        _url() + "/parse",
        files={
            "file": (filename, csv_bytes, "text/plain" if code == 400 else "text/csv")
        },
        data={"usage_date": USAGE_DATE},
    )
    assert resp.status_code == code


async def test_parse_returns_parsed_items(daily_report_csv: bytes, client: AsyncClient):
    """合法 CSV 解析后有 items + batchId 格式正确"""
    resp = await client.post(
        _url() + "/parse",
        files={"file": ("test.csv", daily_report_csv, "text/csv")},
        data={"usage_date": USAGE_DATE},
    )
    assert resp.status_code == 200
    data = resp.json()
    # 验证响应字段（camelCase）
    assert "batchId" in data
    # batchId 应为有效 UUID
    uuid.UUID(data["batchId"])
    assert data["usageDate"] == USAGE_DATE
    assert "parsedItems" in data
    assert "warnings" in data
    # 应解析到 3 个条目（2 labor + 1 machinery）
    assert len(data["parsedItems"]) == 3
    # 每个 item 应有这些字段
    for item in data["parsedItems"]:
        assert "resourceName" in item
        assert "quantity" in item
        assert "category" in item
        assert "mappingStatus" in item
        assert "resourceId" in item
        assert "resourceUnit" in item


# =============================================================================
# confirm-mapping 端点
# =============================================================================


@pytest.mark.parametrize(
    "scenario, code",
    [
        pytest.param("use_existing_match", 200, id="existing_use_existing"),
        pytest.param("create_new", 200, id="missing_create_new"),
        pytest.param("use_existing_mismatch", 400, id="missing_use_existing"),
        pytest.param("create_new_duplicate", 400, id="existing_create_new"),
        pytest.param("missing_batch", 400, id="missing_batch"),
        pytest.param("create_new_category_mismatch", 400, id="labor_block_machinery"),
        pytest.param("create_new_invalid_category", 400, id="labor_block_material"),
    ],
)
async def test_confirm_mapping(
    scenario: str,
    code: int,
    daily_report_csv: bytes,
    resources_for_report,
    client: AsyncClient,
):
    batch_id = await _parse_batch(client, daily_report_csv)

    if scenario == "use_existing_match":
        # dr-r1 已在 resources_for_report fixture 中，USE_EXISTING → 200
        payload = [
            {
                "resourceName": "dr-r1",
                "action": "USE_EXISTING",
                "quantity": 5,
            }
        ]
    elif scenario == "create_new":
        # dr-r2 不存在，CREATE_NEW + new_resource → 200
        payload = [
            {
                "resourceName": "dr-r2",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "dr-r2",
                    "description": "new",
                    "category": "labor",
                },
                "quantity": 3,
            }
        ]
    elif scenario == "use_existing_mismatch":
        # dr-r2 不存在却 USE_EXISTING → 400
        payload = [
            {
                "resourceName": "dr-r2",
                "action": "USE_EXISTING",
                "quantity": 3,
            }
        ]
    elif scenario == "create_new_duplicate":
        # dr-r1 已存在却 CREATE_NEW → 400（业务冲突）
        payload = [
            {
                "resourceName": "dr-r1",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "dr-r1",
                    "description": "new",
                    "category": "labor",
                },
                "quantity": 5,
            }
        ]
    elif scenario in ("create_new_category_mismatch", "create_new_invalid_category"):
        # dr-r2 来自 labor 解析块，但用户提交了非 labor 的 category → 400
        bad_category = (
            "machinery" if scenario == "create_new_category_mismatch" else "material"
        )
        payload = [
            {
                "resourceName": "dr-r2",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "dr-r2",
                    "description": "new",
                    "category": bad_category,
                },
                "quantity": 3,
            }
        ]
    elif scenario == "missing_batch":
        # 不存在的 batch_id → 400
        resp = await client.post(
            _url() + f"/batches/{uuid.uuid4()}/confirm-mapping",
            json=[],
        )
        assert resp.status_code == 400
        return
    else:
        pytest.fail(f"unknown scenario: {scenario}")

    resp = await client.post(
        _url() + f"/batches/{batch_id}/confirm-mapping",
        json=payload,
    )
    assert resp.status_code == code
    if scenario in (
        "create_new_category_mismatch",
        "create_new_invalid_category",
    ):
        # 错误信息应明确指出与解析块不一致，并暴露期望值与实际值
        detail = resp.json().get("detail", "")
        assert "与日报解析块不一致" in detail
        assert "'labor'" in detail
        assert f"'{bad_category}'" in detail


# =============================================================================
# allocate 端点
# =============================================================================


@pytest.mark.parametrize(
    "scenario, code",
    [
        pytest.param("normal", 200, id="normal_allocation"),
        pytest.param("missing_batch", 400, id="missing_batch"),
        pytest.param("quantity_mismatch", 400, id="quantity_mismatch"),
    ],
)
async def test_allocate(
    scenario: str,
    code: int,
    daily_report_csv: bytes,
    resources_for_report,
    tasks_for_report,
    client: AsyncClient,
):
    batch_id = await _parse_batch(client, daily_report_csv)

    if scenario == "missing_batch":
        resp = await client.post(
            _url() + f"/batches/{uuid.uuid4()}/allocate",
            json=[],
        )
        assert resp.status_code == 400
        return

    # 先 confirm dr-r1（USE_EXISTING），dr-r2 (CREATE_NEW)
    confirm_resp = await client.post(
        _url() + f"/batches/{batch_id}/confirm-mapping",
        json=[
            {
                "resourceName": "dr-r1",
                "action": "USE_EXISTING",
                "quantity": 5,
            },
            {
                "resourceName": "dr-r2",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "dr-r2",
                    "description": "new",
                    "category": "labor",
                },
                "quantity": 3,
            },
        ],
    )
    assert confirm_resp.status_code == 200

    # 构造 allocation payload
    if scenario == "quantity_mismatch":
        # dr-r1 的 confirmed 数量是 5，但这里给 999 → 400
        allocations = [
            {
                "resourceName": "dr-r1",
                "taskId": 20001,
                "quantity": 999,
            }
        ]
    else:
        allocations = [
            {
                "resourceName": "dr-r1",
                "taskId": 20001,
                "quantity": 5,
            },
            {
                "resourceName": "dr-r2",
                "taskId": 20002,
                "quantity": 3,
            },
        ]

    resp = await client.post(
        _url() + f"/batches/{batch_id}/allocate",
        json=allocations,
    )
    assert resp.status_code == code
    if code == 200:
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        for item in data:
            assert "resourceName" in item
            assert "quantity" in item
            assert "task" in item


# =============================================================================
# submit 端点
# =============================================================================


@pytest.mark.parametrize(
    "scenario, code",
    [
        pytest.param("complete_flow", 200, id="complete_flow"),
        pytest.param("missing_batch", 400, id="missing_batch"),
    ],
)
async def test_submit(
    scenario: str,
    code: int,
    daily_report_csv: bytes,
    resources_for_report,
    tasks_for_report,
    client: AsyncClient,
):
    if scenario == "missing_batch":
        resp = await client.post(_url() + f"/batches/{uuid.uuid4()}/submit")
        assert resp.status_code == 400
        return

    # 完整流程：parse → confirm → allocate → submit
    batch_id = await _parse_batch(client, daily_report_csv)

    confirm_resp = await client.post(
        _url() + f"/batches/{batch_id}/confirm-mapping",
        json=[
            {
                "resourceName": "dr-r1",
                "action": "USE_EXISTING",
                "quantity": 5,
            },
            {
                "resourceName": "dr-r2",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "dr-r2",
                    "description": "new",
                    "category": "labor",
                },
                "quantity": 3,
            },
        ],
    )
    assert confirm_resp.status_code == 200

    alloc_resp = await client.post(
        _url() + f"/batches/{batch_id}/allocate",
        json=[
            {
                "resourceName": "dr-r1",
                "taskId": 20001,
                "quantity": 5,
            },
            {
                "resourceName": "dr-r2",
                "taskId": 20002,
                "quantity": 3,
            },
        ],
    )
    assert alloc_resp.status_code == 200

    resp = await client.post(_url() + f"/batches/{batch_id}/submit")
    assert resp.status_code == code
    if code == 200:
        data = resp.json()
        assert "batchId" in data
        assert uuid.UUID(data["batchId"]) == uuid.UUID(batch_id)
        assert "importedCount" in data
        assert data["importedCount"] == 2
        assert "taskResourceUsageIds" in data
        assert len(data["taskResourceUsageIds"]) == 2


# =============================================================================
# 重复提交防护（A-2：重复导入 500 → 409）
# =============================================================================


async def _import_once(
    client: AsyncClient, csv_bytes: bytes, filename: str, task_id: int
) -> str:
    """辅助：parse → confirm(仅 dr-r1) → allocate(dr-r1 → task) → 返回 batchId。

    确认映射只提交 dr-r1（USE_EXISTING），dr-r2 跳过、dr-r3 不提交，
    便于重复导入场景复用。
    """
    batch_id = await _parse_batch(client, csv_bytes, filename=filename)
    confirm_resp = await client.post(
        _url() + f"/batches/{batch_id}/confirm-mapping",
        json=[
            {
                "resourceName": "dr-r1",
                "action": "USE_EXISTING",
                "quantity": 5,
            },
            {
                "resourceName": "dr-r2",
                "action": "SKIP",
                "quantity": 3,
            },
        ],
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    alloc_resp = await client.post(
        _url() + f"/batches/{batch_id}/allocate",
        json=[{"resourceName": "dr-r1", "taskId": task_id, "quantity": 5}],
    )
    assert alloc_resp.status_code == 200, alloc_resp.text
    return batch_id


async def _usage_count_for_date(db_session: AsyncSession) -> int:
    """统计 USAGE_DATE 当天的用量行数（验证未被翻倍）。"""
    count = (
        await db_session.exec(
            select(func.count())
            .select_from(TaskResourceUsage)
            .where(TaskResourceUsage.usage_date == date.fromisoformat(USAGE_DATE))
        )
    ).one()
    return count


async def test_submit_duplicate_conflict_409(
    daily_report_csv: bytes,
    resources_for_report,
    tasks_for_report,
    client: AsyncClient,
    db_session: AsyncSession,
):
    """不同文件名、同日期、同工序同资源重复导入 → 409（L1 冲突预检）。"""
    first = await _import_once(client, daily_report_csv, "report-1.csv", 20001)
    resp = await client.post(_url() + f"/batches/{first}/submit")
    assert resp.status_code == 200, resp.text

    second = await _import_once(client, daily_report_csv, "report-2.csv", 20001)
    resp = await client.post(_url() + f"/batches/{second}/submit")
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "已存在相同的资源使用记录" in detail
    assert "DR-T1" in detail
    assert "dr-r1" in detail

    # 原有用量未被翻倍
    assert await _usage_count_for_date(db_session) == 1


async def test_submit_same_file_reimport_409(
    daily_report_csv: bytes,
    resources_for_report,
    tasks_for_report,
    client: AsyncClient,
    db_session: AsyncSession,
):
    """同文件名同日期重复导入（分配到不同工序，pair 不冲突）→ 409（L2 防翻倍）。"""
    first = await _import_once(client, daily_report_csv, "test.csv", 20001)
    resp = await client.post(_url() + f"/batches/{first}/submit")
    assert resp.status_code == 200, resp.text

    # 第二次同文件名，改分配到另一工序（dr-r1 → 20002，pair 不冲突）
    second = await _import_once(client, daily_report_csv, "test.csv", 20002)
    resp = await client.post(_url() + f"/batches/{second}/submit")
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "已由批次" in detail
    assert "导入过" in detail

    # 原有用量未被翻倍
    assert await _usage_count_for_date(db_session) == 1


async def test_submit_reimport_allowed_after_delete(
    daily_report_csv: bytes,
    resources_for_report,
    tasks_for_report,
    client: AsyncClient,
    db_session: AsyncSession,
):
    """删除原记录后，同文件同日期重导应被允许（L2 不产生永久锁）。"""
    first = await _import_once(client, daily_report_csv, "test.csv", 20001)
    resp = await client.post(_url() + f"/batches/{first}/submit")
    assert resp.status_code == 200, resp.text

    # 删除第一次导入的用量行
    rows = (
        await db_session.exec(
            select(TaskResourceUsage).where(
                TaskResourceUsage.batch_id == uuid.UUID(first)
            )
        )
    ).all()
    for row in rows:
        await db_session.delete(row)
    await db_session.commit()

    # 同文件同日期重导 → 200
    second = await _import_once(client, daily_report_csv, "test.csv", 20001)
    resp = await client.post(_url() + f"/batches/{second}/submit")
    assert resp.status_code == 200, resp.text
    assert resp.json()["importedCount"] == 1


# =============================================================================
# 跨项目隔离
# =============================================================================


async def test_daily_report_project_404(client: AsyncClient):
    """不存在的 project_id 应返回 404"""
    csv_bytes = _build_csv_bytes()
    resp = await client.post(
        _url(pid=9999) + "/parse",
        files={"file": ("test.csv", csv_bytes, "text/csv")},
        data={"usage_date": USAGE_DATE},
    )
    assert resp.status_code == 404
