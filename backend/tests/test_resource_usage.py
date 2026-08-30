"""Resource usage API 测试。"""
# pyright: reportCallIssue=false

import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.daily_report import ImportBatch, ImportBatchStatus
from src.models.resource import Resource, ResourceCategory
from src.models.resource_usage import TaskResourceUsage
from src.models.tag import Tag, TagDimension, UsageTag
from src.models.task import Task

# 默认项目 id（由 alembic 迁移 10f6fdbf450e seed）
PID = 1

# fixture 使用大 id 范围（10000+），避开 alembic seed resource 数据（max id ~2496）
T_ID_BASE = 10000
R_ID_BASE = 10100
U_ID_BASE = 10200

# 固定 batch_id（便于参数化）
FIXED_BATCH = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest_asyncio.fixture
async def task_resources(db_session: AsyncSession):
    """插入 2 task、3 resource、5 task_resource_usage 记录"""
    tasks = [
        Task(
            id=T_ID_BASE + 1,
            project_id=PID,
            code="T-001",
            name="T1",
            duration=5.0,
            completed=0.0,
        ),
        Task(
            id=T_ID_BASE + 2,
            project_id=PID,
            code="T-002",
            name="T2",
            duration=5.0,
            completed=0.0,
        ),
    ]
    resources = [
        Resource(
            id=R_ID_BASE + 1,
            project_id=PID,
            name="ru-r1",
            description="d1",
            category=ResourceCategory.labor,
        ),
        Resource(
            id=R_ID_BASE + 2,
            project_id=PID,
            name="ru-r2",
            description="d2",
            category=ResourceCategory.machinery,
        ),
        Resource(
            id=R_ID_BASE + 3,
            project_id=PID,
            name="ru-r3",
            description="d3",
            category=ResourceCategory.material,
        ),
    ]
    usages = [
        # id=10200: task=10001, resource=10101, date=2026-06-01, qty=10.0
        TaskResourceUsage(
            id=U_ID_BASE,
            project_id=PID,
            task_id=T_ID_BASE + 1,
            resource_id=R_ID_BASE + 1,
            usage_date=date(2026, 6, 1),
            quantity=10.0,
        ),
        # id=10201: task=10001, resource=10102, date=2026-06-01, qty=5.0
        TaskResourceUsage(
            id=U_ID_BASE + 1,
            project_id=PID,
            task_id=T_ID_BASE + 1,
            resource_id=R_ID_BASE + 2,
            usage_date=date(2026, 6, 1),
            quantity=5.0,
        ),
        # id=10202: task=10001, resource=10101, date=2026-06-02, qty=8.0
        TaskResourceUsage(
            id=U_ID_BASE + 2,
            project_id=PID,
            task_id=T_ID_BASE + 1,
            resource_id=R_ID_BASE + 1,
            usage_date=date(2026, 6, 2),
            quantity=8.0,
        ),
        # id=10203: task=10002, resource=10101, date=2026-06-01, qty=20.0
        TaskResourceUsage(
            id=U_ID_BASE + 3,
            project_id=PID,
            task_id=T_ID_BASE + 2,
            resource_id=R_ID_BASE + 1,
            usage_date=date(2026, 6, 1),
            quantity=20.0,
        ),
        # id=10204:
        # task=10002, resource=10103, date=2026-06-03, qty=3.0, batch=FIXED_BATCH
        TaskResourceUsage(
            id=U_ID_BASE + 4,
            project_id=PID,
            task_id=T_ID_BASE + 2,
            resource_id=R_ID_BASE + 3,
            usage_date=date(2026, 6, 3),
            quantity=3.0,
            batch_id=FIXED_BATCH,
        ),
    ]
    # 必须分三次 commit：先 task/resource（被引用），
    # 再 import_batch（被 usage.batch_id 引用），最后插入 usage
    db_session.add_all(tasks + resources)
    await db_session.commit()
    batch = ImportBatch(
        id=FIXED_BATCH,
        project_id=PID,
        original_filename="test.csv",
        usage_date=date(2026, 6, 3),
        total_rows=1,
        imported_rows=1,
        status=ImportBatchStatus.COMPLETED,
    )
    db_session.add(batch)
    await db_session.commit()
    db_session.add_all(usages)
    await db_session.commit()
    return usages


def _url(pid: int = PID) -> str:
    return f"/projects/{pid}/resource-usage"


@pytest.mark.parametrize(
    "ru_id, exists",
    [
        pytest.param(U_ID_BASE, True, id="first"),
        pytest.param(U_ID_BASE + 4, True, id="last_with_batch"),
        pytest.param(99999, False, id="not_found"),
    ],
)
async def test_get_resource_usage(
    task_resources, client: AsyncClient, ru_id: int, exists: bool
):
    resp = await client.get(f"{_url()}/{ru_id}")
    if exists:
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == ru_id
        assert "taskId" in data
        assert "resourceId" in data
        assert "usageDate" in data
        assert "quantity" in data
        assert "batchId" in data
        assert "createdAt" in data
        assert "updatedAt" in data
    else:
        assert resp.status_code == 404


@pytest.mark.parametrize(
    "params, expected_total",
    [
        pytest.param({}, 5, id="all"),
        pytest.param({"resource_ids": [R_ID_BASE + 1]}, 3, id="filter_resource_1"),
        pytest.param({"task_ids": [T_ID_BASE + 1]}, 3, id="filter_task_1"),
        pytest.param(
            {"resource_ids": [R_ID_BASE + 1], "task_ids": [T_ID_BASE + 2]},
            1,
            id="filter_both",
        ),
        pytest.param({"date": "2026-06-01"}, 3, id="filter_date_only"),
        pytest.param(
            {"date": "2026-06-01", "resource_ids": [R_ID_BASE + 1]},
            2,
            id="filter_date_and_resource",
        ),
        pytest.param({"batch_id": str(FIXED_BATCH)}, 1, id="filter_batch"),
        pytest.param({"page": "1", "per_page": "2"}, 5, id="page1_per_page2"),
        pytest.param({"page": "3", "per_page": "2"}, 5, id="page3_per_page2"),
    ],
)
async def test_list_resource_usages(
    task_resources,
    client: AsyncClient,
    params: dict,
    expected_total: int,
):
    resp = await client.get(_url(), params=params)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == expected_total
    # items 长度校验（仅在分页参数有效时）
    if "page" in params and "per_page" in params:
        page = int(params["page"])
        per_page = int(params["per_page"])
        expected_items = min(per_page, max(0, expected_total - (page - 1) * per_page))
        assert len(data["items"]) == expected_items


@pytest.mark.parametrize(
    "ru_id, payload, code",
    [
        pytest.param(99999, {"quantity": 5.0}, 404, id="not_found"),
        pytest.param(U_ID_BASE, {}, 200, id="empty_payload"),
        pytest.param(U_ID_BASE, {"quantity": 99.5}, 200, id="update_quantity"),
        pytest.param(
            U_ID_BASE,
            # 与 fixture id=10203 (task=10002, resource=10101, date=2026-06-01) 冲突
            {
                "task_id": T_ID_BASE + 2,
                "resource_id": R_ID_BASE + 1,
                "usage_date": "2026-06-01",
            },
            409,
            id="conflict_with_other",
        ),
        pytest.param(
            U_ID_BASE,
            # 把 task_id 改为不存在的 → FK violation → 422
            {"task_id": 999999},
            422,
            id="fk_task_missing",
        ),
        pytest.param(
            U_ID_BASE,
            # 把 resource_id 改为不存在的 → FK violation → 422
            {"resource_id": 999999},
            422,
            id="fk_resource_missing",
        ),
        pytest.param(U_ID_BASE, {"quantity": -1.0}, 422, id="invalid_quantity"),
    ],
)
async def test_update_resource_usage(
    task_resources,
    client: AsyncClient,
    ru_id: int,
    payload: dict,
    code: int,
):
    resp = await client.put(f"{_url()}/{ru_id}", json=payload)
    assert resp.status_code == code


@pytest.mark.parametrize(
    "ru_id, code",
    [
        pytest.param(99999, 404, id="not_found"),
        pytest.param(U_ID_BASE + 4, 204, id="success"),
    ],
)
async def test_delete_resource_usage(
    task_resources, client: AsyncClient, ru_id: int, code: int
):
    resp = await client.delete(f"{_url()}/{ru_id}")
    assert resp.status_code == code
    if code == 204:
        assert resp.content == b""
        # 删除后 GET 返回 404
        get_resp = await client.get(f"{_url()}/{ru_id}")
        assert get_resp.status_code == 404


async def test_resource_usage_project_404(client: AsyncClient):
    """不存在的 project_id 应返回 404（依赖 _get_current_project）"""
    resp = await client.get(_url(pid=9999))
    assert resp.status_code == 404
    resp = await client.get(f"{_url(pid=9999)}/1")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /resource-usage/batch — 批量创建
# ---------------------------------------------------------------------------


def _batch_url(pid: int = PID) -> str:
    return f"/projects/{pid}/resource-usage/batch"


async def test_batch_create_single_item(task_resources, client: AsyncClient):
    """单条记录批量创建 → 返回 201 + batch 信息"""
    payload = {
        "name": "测试批次",
        "items": [
            {
                "task_id": T_ID_BASE + 1,
                "resource_id": R_ID_BASE + 1,
                "usage_date": "2026-06-10",
                "quantity": 5.0,
            }
        ],
    }
    resp = await client.post(_batch_url(), json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "batch" in data
    assert data["batch"]["name"] == "测试批次"
    assert data["batch"]["recordCount"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["taskId"] == T_ID_BASE + 1
    assert item["resourceId"] == R_ID_BASE + 1
    assert item["quantity"] == 5.0
    assert item["manualBatchId"] == data["batch"]["id"]
    assert item["batchId"] is None
    # 嵌套 manual_batch 应随响应一并返回
    assert item["manualBatch"] is not None
    assert item["manualBatch"]["id"] == data["batch"]["id"]
    assert item["manualBatch"]["name"] == "测试批次"
    assert item["manualBatch"]["recordCount"] == 1
    assert item["manualBatch"]["projectId"] == PID


async def test_batch_create_multiple_items(task_resources, client: AsyncClient):
    """多条记录批量创建 → 返回 201 + 所有关联到同一 batch"""
    payload = {
        "name": "多条批次",
        "items": [
            {
                "task_id": T_ID_BASE + 1,
                "resource_id": R_ID_BASE + 1,
                "usage_date": "2026-06-11",
                "quantity": 2.0,
            },
            {
                "task_id": T_ID_BASE + 2,
                "resource_id": R_ID_BASE + 2,
                "usage_date": "2026-06-11",
                "quantity": 3.0,
            },
            {
                "task_id": T_ID_BASE + 1,
                "resource_id": R_ID_BASE + 3,
                "usage_date": "2026-06-11",
                "quantity": 1.5,
            },
        ],
    }
    resp = await client.post(_batch_url(), json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["batch"]["recordCount"] == 3
    assert len(data["items"]) == 3
    batch_id = data["batch"]["id"]
    for item in data["items"]:
        assert item["manualBatchId"] == batch_id
        # 嵌套 manual_batch 也应被填充且字段一致
        assert item["manualBatch"] is not None
        assert item["manualBatch"]["id"] == batch_id
        assert item["manualBatch"]["name"] == "多条批次"
        assert item["manualBatch"]["recordCount"] == 3


async def test_batch_create_empty_items(task_resources, client: AsyncClient):
    """空 items 列表 → 422"""
    payload = {"name": "空批次", "items": []}
    resp = await client.post(_batch_url(), json=payload)
    assert resp.status_code == 422


async def test_batch_create_missing_name(task_resources, client: AsyncClient):
    """缺少 name → 422"""
    payload = {
        "items": [
            {
                "task_id": T_ID_BASE + 1,
                "resource_id": R_ID_BASE + 1,
                "usage_date": "2026-06-10",
                "quantity": 5.0,
            }
        ]
    }
    resp = await client.post(_batch_url(), json=payload)
    assert resp.status_code == 422


async def test_batch_create_negative_quantity(task_resources, client: AsyncClient):
    """quantity <= 0 → 422"""
    payload = {
        "name": "负数批次",
        "items": [
            {
                "task_id": T_ID_BASE + 1,
                "resource_id": R_ID_BASE + 1,
                "usage_date": "2026-06-10",
                "quantity": -1.0,
            }
        ],
    }
    resp = await client.post(_batch_url(), json=payload)
    assert resp.status_code == 422


async def test_batch_create_zero_quantity(task_resources, client: AsyncClient):
    """quantity = 0 → 422"""
    payload = {
        "name": "零值批次",
        "items": [
            {
                "task_id": T_ID_BASE + 1,
                "resource_id": R_ID_BASE + 1,
                "usage_date": "2026-06-10",
                "quantity": 0,
            }
        ],
    }
    resp = await client.post(_batch_url(), json=payload)
    assert resp.status_code == 422


async def test_batch_create_fk_task_missing(task_resources, client: AsyncClient):
    """task_id 不存在 → 422"""
    payload = {
        "name": "FK测试",
        "items": [
            {
                "task_id": 999999,
                "resource_id": R_ID_BASE + 1,
                "usage_date": "2026-06-10",
                "quantity": 5.0,
            }
        ],
    }
    resp = await client.post(_batch_url(), json=payload)
    assert resp.status_code == 422


async def test_batch_create_fk_resource_missing(task_resources, client: AsyncClient):
    """resource_id 不存在 → 422"""
    payload = {
        "name": "FK测试",
        "items": [
            {
                "task_id": T_ID_BASE + 1,
                "resource_id": 999999,
                "usage_date": "2026-06-10",
                "quantity": 5.0,
            }
        ],
    }
    resp = await client.post(_batch_url(), json=payload)
    assert resp.status_code == 422


async def test_batch_create_duplicate_key(task_resources, client: AsyncClient):
    """与已有记录冲突 → 409"""
    payload = {
        "name": "冲突批次",
        "items": [
            {
                # 与 fixture id=10200 (task=10001, resource=10101, date=2026-06-01) 冲突
                "task_id": T_ID_BASE + 1,
                "resource_id": R_ID_BASE + 1,
                "usage_date": "2026-06-01",
                "quantity": 9.0,
            }
        ],
    }
    resp = await client.post(_batch_url(), json=payload)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /resource-usage?manual_batch_id=X — 手动批次过滤
# ---------------------------------------------------------------------------


async def test_list_filter_manual_batch_id(task_resources, client: AsyncClient):
    """通过 manual_batch_id 过滤 → 仅返回该批次的记录"""
    # 先创建一个 batch
    create_resp = await client.post(
        _batch_url(),
        json={
            "name": "过滤测试",
            "items": [
                {
                    "task_id": T_ID_BASE + 1,
                    "resource_id": R_ID_BASE + 2,
                    "usage_date": "2026-06-20",
                    "quantity": 4.0,
                },
                {
                    "task_id": T_ID_BASE + 2,
                    "resource_id": R_ID_BASE + 2,
                    "usage_date": "2026-06-20",
                    "quantity": 6.0,
                },
            ],
        },
    )
    assert create_resp.status_code == 201
    batch_id = create_resp.json()["batch"]["id"]

    # 按 manual_batch_id 过滤
    resp = await client.get(_url(), params={"manual_batch_id": batch_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["manualBatchId"] == batch_id


async def test_list_filter_manual_batch_id_empty(task_resources, client: AsyncClient):
    """不存在的 manual_batch_id → 返回空"""
    resp = await client.get(_url(), params={"manual_batch_id": 999999})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_list_filter_source_import(task_resources, client: AsyncClient):
    """batch_id 过滤 → 仅返回导入记录"""
    resp = await client.get(_url(), params={"batch_id": str(FIXED_BATCH)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["batchId"] == str(FIXED_BATCH)
    assert data["items"][0]["manualBatchId"] is None


# ---------------------------------------------------------------------------
# GET /resource-usage/{id} — 响应包含 manualBatchId
# ---------------------------------------------------------------------------


async def test_get_includes_manual_batch_id(task_resources, client: AsyncClient):
    """GET 单条记录返回 manualBatchId 字段"""
    # 创建 batch 记录
    create_resp = await client.post(
        _batch_url(),
        json={
            "name": "详情测试",
            "items": [
                {
                    "task_id": T_ID_BASE + 1,
                    "resource_id": R_ID_BASE + 1,
                    "usage_date": "2026-06-25",
                    "quantity": 7.0,
                }
            ],
        },
    )
    ru_id = create_resp.json()["items"][0]["id"]
    batch_id = create_resp.json()["batch"]["id"]

    resp = await client.get(f"{_url()}/{ru_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["manualBatchId"] == batch_id
    assert data["batchId"] is None
    # 嵌套 manual_batch 也应被填充，包含全部 ManualSubmissionBatchResp 字段
    assert data["manualBatch"] is not None
    assert data["manualBatch"]["id"] == batch_id
    assert data["manualBatch"]["name"] == "详情测试"
    assert data["manualBatch"]["recordCount"] == 1
    assert data["manualBatch"]["projectId"] == PID
    assert "createdAt" in data["manualBatch"]
    assert "updatedAt" in data["manualBatch"]

    # 反向：fixture 中 U_ID_BASE 没有 manual_batch_id → manualBatch 应为 None
    none_resp = await client.get(f"{_url()}/{U_ID_BASE}")
    assert none_resp.status_code == 200
    none_data = none_resp.json()
    assert none_data["manualBatchId"] is None
    assert none_data["manualBatch"] is None


# ---------------------------------------------------------------------------
# PUT /resource-usage/{id} — batch 字段不可变
# ---------------------------------------------------------------------------


async def test_update_ignores_batch_fields(task_resources, client: AsyncClient):
    """PUT 带 batch_id/manual_batch_id → 字段被忽略，记录不变"""
    resp = await client.put(
        f"{_url()}/{U_ID_BASE}",
        json={
            "quantity": 88.8,
            "batch_id": "00000000-0000-0000-0000-000000000000",
            "manual_batch_id": 99999,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["quantity"] == 88.8
    # batch 字段不应被修改
    assert data["batchId"] is None
    assert data["manualBatchId"] is None


async def test_list_includes_manual_batch_per_item(task_resources, client: AsyncClient):
    """GET 列表中每条记录都应正确填充 manualBatch 嵌套对象（或为 None）"""
    # 创建两个不同的 manual_batch
    resp_a = await client.post(
        _batch_url(),
        json={
            "name": "ListBatchA",
            "items": [
                {
                    "task_id": T_ID_BASE + 1,
                    "resource_id": R_ID_BASE + 3,
                    "usage_date": "2026-07-01",
                    "quantity": 1.0,
                }
            ],
        },
    )
    resp_b = await client.post(
        _batch_url(),
        json={
            "name": "ListBatchB",
            "items": [
                {
                    "task_id": T_ID_BASE + 2,
                    "resource_id": R_ID_BASE + 3,
                    "usage_date": "2026-07-02",
                    "quantity": 2.0,
                }
            ],
        },
    )
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201
    a_id = resp_a.json()["batch"]["id"]
    b_id = resp_b.json()["batch"]["id"]
    assert a_id != b_id

    # 用 manual_batch_id 过滤后，列表中每条都应带正确的嵌套 manual_batch
    list_resp_a = await client.get(
        _url(), params={"manual_batch_id": a_id, "per_page": "50"}
    )
    assert list_resp_a.status_code == 200
    items_a = list_resp_a.json()["items"]
    assert items_a, "应当返回至少一条记录"
    for it in items_a:
        assert it["manualBatchId"] == a_id
        assert it["manualBatch"] is not None
        assert it["manualBatch"]["id"] == a_id
        assert it["manualBatch"]["name"] == "ListBatchA"

    list_resp_b = await client.get(
        _url(), params={"manual_batch_id": b_id, "per_page": "50"}
    )
    assert list_resp_b.status_code == 200
    items_b = list_resp_b.json()["items"]
    assert items_b
    for it in items_b:
        assert it["manualBatchId"] == b_id
        assert it["manualBatch"] is not None
        assert it["manualBatch"]["id"] == b_id
        assert it["manualBatch"]["name"] == "ListBatchB"


async def test_put_includes_manual_batch(task_resources, client: AsyncClient):
    """PUT 更新后响应中应包含 manualBatch 嵌套对象"""
    create_resp = await client.post(
        _batch_url(),
        json={
            "name": "PutBatch",
            "items": [
                {
                    "task_id": T_ID_BASE + 1,
                    "resource_id": R_ID_BASE + 1,
                    "usage_date": "2026-07-05",
                    "quantity": 3.0,
                }
            ],
        },
    )
    assert create_resp.status_code == 201
    ru_id = create_resp.json()["items"][0]["id"]
    batch_id = create_resp.json()["batch"]["id"]

    put_resp = await client.put(f"{_url()}/{ru_id}", json={"quantity": 9.0})
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["quantity"] == 9.0
    assert data["manualBatchId"] == batch_id
    assert data["manualBatch"] is not None
    assert data["manualBatch"]["id"] == batch_id
    assert data["manualBatch"]["name"] == "PutBatch"


# ---------------------------------------------------------------------------
# POST /resource-usage — 已移除，应返回 405
# ---------------------------------------------------------------------------


async def test_single_create_returns_405(task_resources, client: AsyncClient):
    """单条 POST 已移除 → 405 Method Not Allowed"""
    resp = await client.post(
        _url(),
        json={
            "task_id": T_ID_BASE + 1,
            "resource_id": R_ID_BASE + 1,
            "usage_date": "2026-06-10",
            "quantity": 5.0,
        },
    )
    assert resp.status_code == 405


# ---------------------------------------------------------------------------
# batch 创建后的 GET /resource-usage 列表验证
# ---------------------------------------------------------------------------


async def test_batch_created_records_appear_in_list(
    task_resources, client: AsyncClient
):
    """batch 创建的记录出现在全局列表中"""
    # 获取创建前总数
    before = (await client.get(_url())).json()["total"]

    # 创建 batch
    await client.post(
        _batch_url(),
        json={
            "name": "列表验证",
            "items": [
                {
                    "task_id": T_ID_BASE + 1,
                    "resource_id": R_ID_BASE + 1,
                    "usage_date": "2026-06-30",
                    "quantity": 1.0,
                },
                {
                    "task_id": T_ID_BASE + 2,
                    "resource_id": R_ID_BASE + 2,
                    "usage_date": "2026-06-30",
                    "quantity": 2.0,
                },
            ],
        },
    )

    # 验证总数增加
    after = (await client.get(_url())).json()["total"]
    assert after == before + 2


# ---------------------------------------------------------------------------
# GET /resource-usage — 列表携带直接标签（include_tags 开关）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tagged_usages(task_resources, db_session: AsyncSession):
    """在 task_resources 基础上新增标签维度、标签与用量-标签关联。"""
    dim = TagDimension(project_id=PID, name="用量测试维度", description="d")
    db_session.add(dim)
    await db_session.commit()
    await db_session.refresh(dim)
    assert dim.id is not None

    tag_a = Tag(project_id=PID, dimension_id=dim.id, name="ru-tag-A", description="d")
    tag_b = Tag(project_id=PID, dimension_id=dim.id, name="ru-tag-B", description="d")
    db_session.add_all([tag_a, tag_b])
    await db_session.commit()
    await db_session.refresh(tag_a)
    await db_session.refresh(tag_b)
    assert tag_a.id is not None and tag_b.id is not None

    # U_ID_BASE → tag_b（乱序）、tag_a；U_ID_BASE+1 → tag_a；其余无标签
    db_session.add_all([
        UsageTag(project_id=PID, usage_id=U_ID_BASE, tag_id=tag_b.id),
        UsageTag(project_id=PID, usage_id=U_ID_BASE, tag_id=tag_a.id),
        UsageTag(project_id=PID, usage_id=U_ID_BASE + 1, tag_id=tag_a.id),
    ])
    await db_session.commit()
    return task_resources


async def test_list_resource_usages_tags_empty_by_default(
    tagged_usages, client: AsyncClient
):
    """默认不带 include_tags 时，每条用量记录返回空 tags 列表。"""
    resp = await client.get(_url(), params={"per_page": "100"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 5
    assert all(it["tags"] == [] for it in items)


async def test_list_resource_usages_include_tags(tagged_usages, client: AsyncClient):
    """include_tags=true 时返回直接标签（按 ID 升序），无标签记录返回空数组。"""
    resp = await client.get(_url(), params={"include_tags": "true", "per_page": "100"})
    assert resp.status_code == 200
    by_id = {it["id"]: it for it in resp.json()["items"]}

    assert [t["name"] for t in by_id[U_ID_BASE]["tags"]] == ["ru-tag-A", "ru-tag-B"]
    assert [t["name"] for t in by_id[U_ID_BASE + 1]["tags"]] == ["ru-tag-A"]
    assert by_id[U_ID_BASE + 2]["tags"] == []
    assert by_id[U_ID_BASE + 3]["tags"] == []
    assert by_id[U_ID_BASE + 4]["tags"] == []


async def test_list_resource_usages_include_tags_pagination(
    tagged_usages, client: AsyncClient
):
    """分页只加载当前页用量记录的标签，跨页不串数据。"""
    # 按 id 倒序（最新在前），page=4 取 id=U_ID_BASE+1（有标签），
    # page=5 取 id=U_ID_BASE（有标签）
    resp = await client.get(
        _url(), params={"include_tags": "true", "per_page": "1", "page": "4"}
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == U_ID_BASE + 1
    assert [t["name"] for t in items[0]["tags"]] == ["ru-tag-A"]


async def test_list_resource_usages_include_tags_project_isolated(
    tagged_usages,
    client: AsyncClient,
    db_session: AsyncSession,
):
    """其他项目挂同名标签的用量记录不串入本项目列表。"""
    from src.models.project import Project

    other = Project(name="用量标签隔离项目", is_active=True)
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    assert other.id is not None

    other_res = Resource(
        project_id=other.id,
        name="ru-other-r",
        description="d",
        category=ResourceCategory.material,
    )
    other_task = Task(
        project_id=other.id,
        code="RU-OTHER",
        name="其他任务",
        duration=5.0,
        completed=0.0,
    )
    db_session.add_all([other_res, other_task])
    await db_session.commit()
    await db_session.refresh(other_res)
    await db_session.refresh(other_task)
    assert other_res.id is not None and other_task.id is not None

    other_usage = TaskResourceUsage(
        project_id=other.id,
        task_id=other_task.id,
        resource_id=other_res.id,
        usage_date=date(2026, 6, 5),
        quantity=1.0,
    )
    db_session.add(other_usage)
    await db_session.commit()
    await db_session.refresh(other_usage)
    assert other_usage.id is not None

    other_dim = TagDimension(project_id=other.id, name="其他维度", description="d")
    db_session.add(other_dim)
    await db_session.commit()
    await db_session.refresh(other_dim)
    assert other_dim.id is not None
    other_tag = Tag(
        project_id=other.id, dimension_id=other_dim.id, name="ru-tag-A", description="d"
    )
    db_session.add(other_tag)
    await db_session.commit()
    await db_session.refresh(other_tag)
    assert other_tag.id is not None
    db_session.add(
        UsageTag(project_id=other.id, usage_id=other_usage.id, tag_id=other_tag.id)
    )
    await db_session.commit()

    resp = await client.get(_url(), params={"include_tags": "true", "per_page": "100"})
    assert resp.status_code == 200
    by_id = {it["id"]: it for it in resp.json()["items"]}
    assert other_usage.id not in by_id
    assert [t["name"] for t in by_id[U_ID_BASE]["tags"]] == ["ru-tag-A", "ru-tag-B"]
    assert [t["name"] for t in by_id[U_ID_BASE + 1]["tags"]] == ["ru-tag-A"]


async def test_list_resource_usages_include_tags_with_filters(
    tagged_usages, client: AsyncClient
):
    """include_tags 与既有过滤条件（task_ids）组合使用。"""
    resp = await client.get(
        _url(),
        params={
            "task_ids": [T_ID_BASE + 1],
            "include_tags": "true",
            "per_page": "100",
        },
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    ids = {it["id"] for it in items}
    assert ids == {U_ID_BASE, U_ID_BASE + 1, U_ID_BASE + 2}
    by_id = {it["id"]: it for it in items}
    assert [t["name"] for t in by_id[U_ID_BASE]["tags"]] == ["ru-tag-A", "ru-tag-B"]
    assert [t["name"] for t in by_id[U_ID_BASE + 1]["tags"]] == ["ru-tag-A"]
    assert by_id[U_ID_BASE + 2]["tags"] == []
