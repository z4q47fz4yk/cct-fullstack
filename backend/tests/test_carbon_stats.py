"""测试资源用量碳排放统计端点、usage_type 端到端往返、Project CRUD 烟雾。

覆盖最近三个新功能：
- 多项目管理（Project + CurrentProject 依赖）
- usage_type 字段（ACTUAL/PLANNED）
- GET /projects/{project_id}/resource-usage/stats/carbon 端点
  （原 /optimize/monthly-emissions 迁移而来；只聚合 usage 表，
   PLANNED 仅支持月粒度，day/week 返回 422；响应为 period/periodIndex。）

按 tests/AGENTS.md 规范，使用 tests/conftest.py 的现有 fixtures。
"""
# pyright: reportCallIssue=false

from datetime import date

import pytest
import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.task import Task
from src.schemas.resource import ResourceCategory

# ============================================================
# Fixtures
# ============================================================


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    """测试项目（CurrentProject 依赖需要）。

    不显式指定 id，让数据库自动分配——测试数据库可能已含 id=1 的默认项目。
    """
    p = Project(name="Test Project", is_active=True)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def resources(db_session: AsyncSession, project: Project) -> list[Resource]:
    """两个 carbon_factor 非对称的资源，便于检测乘法错误"""
    pid = project.id
    assert pid is not None
    rs = [
        Resource(
            project_id=pid,
            name="R1-Material",
            description="d",
            category=ResourceCategory.material,
            carbon_factor=0.9,
        ),
        Resource(
            project_id=pid,
            name="R2-Labor",
            description="d",
            category=ResourceCategory.labor,
            carbon_factor=2.7,
        ),
    ]
    db_session.add_all(rs)
    await db_session.commit()
    for r in rs:
        await db_session.refresh(r)
    return rs


@pytest_asyncio.fixture
async def task(db_session: AsyncSession, project: Project) -> Task:
    pid = project.id
    assert pid is not None
    t = Task(
        project_id=pid,
        code="TC-001",
        name="T1",
        duration=5.0,
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def usage_records(
    db_session: AsyncSession,
    project: Project,
    resources: list[Resource],
    task: Task,
) -> list[TaskResourceUsage]:
    """5 条混合 ACTUAL/PLANNED 的用量记录，跨 1-2 月，跨资源 1/2。

    设计目的：让 ACTUAL vs PLANNED 关键不变量的数值精确可验证。

    数值表（carbon_factor: r1=0.9, r2=2.7）：
        Jan r1 ACTUAL  qty=10  emission=9.0
        Jan r1 PLANNED  qty=5   emission=4.5
        Jan r2 ACTUAL  qty=20  emission=54.0
        Feb r1 ACTUAL  qty=15  emission=13.5
        Feb r2 PLANNED qty=100 emission=270.0   <- 仅 PLANNED（用于验证排除）

    ACTUAL 总 emission = 9.0 + 54.0 + 13.5 = 76.5
    PLANNED 总 emission = 4.5 + 270.0 = 274.5
    """
    pid = project.id
    tid = task.id
    r0id = resources[0].id
    r1id = resources[1].id
    assert pid is not None
    assert tid is not None
    assert r0id is not None
    assert r1id is not None
    rows = [
        TaskResourceUsage(
            project_id=pid,
            task_id=tid,
            resource_id=r0id,
            usage_date=date(2026, 1, 15),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=tid,
            resource_id=r0id,
            usage_date=date(2026, 1, 20),
            quantity=5.0,
            usage_type=UsageType.PLANNED,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=tid,
            resource_id=r1id,
            usage_date=date(2026, 1, 10),
            quantity=20.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=tid,
            resource_id=r0id,
            usage_date=date(2026, 2, 5),
            quantity=15.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=tid,
            resource_id=r1id,
            usage_date=date(2026, 2, 12),
            quantity=100.0,
            usage_type=UsageType.PLANNED,
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return rows


# ============================================================
# A. Project CRUD 烟雾测试
# ============================================================


async def test_project_crud_smoke(client: AsyncClient, project: Project):
    """Project CRUD 完整流程：create → get → list → delete。"""
    # get
    resp = await client.get(f"/project/{project.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == project.id
    assert data["name"] == project.name
    assert data["is_active"] is True

    # list (smoke: 含项目 id 即可)
    resp = await client.get("/project")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(item["id"] == project.id for item in body["items"])

    # create
    resp = await client.post(
        "/project", json={"name": "Other Project", "description": "d"}
    )
    assert resp.status_code == 201
    new_id = resp.json()["id"]
    assert new_id != project.id

    # delete the new one
    resp = await client.delete(f"/project/{new_id}")
    assert resp.status_code == 204


# ============================================================
# B. usage_type 端到端往返
# ============================================================


async def test_create_usage_omits_type_defaults_actual(
    db_session: AsyncSession,
    project: Project,
    resources: list[Resource],
    task: Task,
):
    """不传 usageType 创建 → DB 默认 ACTUAL（向后兼容 daily_report.submit）。

    注：直接通过 db_session 插入验证 default；不通过 POST 端点，
    因为 ResourceUsageResp.created_at/updated_at 是 str 而 ORM 是 datetime
    （预存的 schema/model 类型不一致，与本次改动无关）。
    """
    pid = project.id
    tid = task.id
    r0id = resources[0].id
    assert pid is not None
    assert tid is not None
    assert r0id is not None
    usage = TaskResourceUsage(
        project_id=pid,
        task_id=tid,
        resource_id=r0id,
        usage_date=date(2026, 3, 15),
        quantity=5.0,
    )
    # 未传 usage_type，应默认为 ACTUAL
    assert usage.usage_type == UsageType.ACTUAL

    db_session.add(usage)
    await db_session.commit()
    await db_session.refresh(usage)
    assert usage.usage_type == UsageType.ACTUAL


async def test_create_usage_with_planned(
    db_session: AsyncSession,
    project: Project,
    resources: list[Resource],
    task: Task,
):
    """显式 usage_type=PLANNED 创建 → DB 中存储 PLANNED。"""
    pid = project.id
    tid = task.id
    r0id = resources[0].id
    assert pid is not None
    assert tid is not None
    assert r0id is not None
    usage = TaskResourceUsage(
        project_id=pid,
        task_id=tid,
        resource_id=r0id,
        usage_date=date(2026, 4, 1),
        quantity=100.0,
        usage_type=UsageType.PLANNED,
    )
    db_session.add(usage)
    await db_session.commit()
    await db_session.refresh(usage)
    assert usage.usage_type == UsageType.PLANNED


async def test_create_usage_with_invalid_type_via_pydantic():
    """Pydantic StrEnum 校验：非法字符串无法通过 schema 验证。"""
    from pydantic import ValidationError

    from src.schemas.resource_usage import ResourceUsageBatchItem

    with pytest.raises(ValidationError):
        ResourceUsageBatchItem(
            task_id=1,
            resource_id=1,
            usage_date=date(2026, 3, 15),
            quantity=5.0,
            usage_type="INVALID",  # type: ignore[arg-type]
        )


async def test_list_usage_filters_by_type(
    client: AsyncClient,
    project: Project,
    usage_records: list[TaskResourceUsage],
):
    """GET ?usageType=PLANNED → 仅返回 PLANNED 行（fixture 含 2 条 PLANNED）。"""
    resp = await client.get(f"/projects/{project.id}/resource-usage?usageType=PLANNED")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    for item in body["items"]:
        assert item["usageType"] == "PLANNED"


# ============================================================
# C. 碳排放统计端点（/resource-usage/stats/carbon）
# ============================================================


async def test_carbon_stats_actual_required(
    client: AsyncClient,
    project: Project,
    usage_records: list[TaskResourceUsage],
):
    """usageType 必填：缺省返回 422（不再有合并 ACTUAL+PLANNED 的暗分支）。"""
    resp = await client.get(f"/projects/{project.id}/resource-usage/stats/carbon")
    assert resp.status_code == 422


async def test_carbon_stats_month_actual_exact_values(
    client: AsyncClient,
    project: Project,
    usage_records: list[TaskResourceUsage],
):
    """默认粒度 month + usageType=ACTUAL，精确数值与结构字段。"""
    resp = await client.get(
        f"/projects/{project.id}/resource-usage/stats/carbon?usageType=ACTUAL"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # 3 ACTUAL 条：Jan r1=9.0, Jan r2=54.0, Feb r1=13.5
    assert data["totalPeriods"] == 2
    assert data["totalResources"] == 2
    assert len(data["items"]) == 3

    total_emission = sum(item["emission"] for item in data["items"])
    assert total_emission == pytest.approx(76.5)

    # 响应无 startMonth/endMonth/source 旧字段
    assert "startMonth" not in data
    assert "endMonth" not in data
    assert "source" not in data

    # period/periodIndex 递增（月粒度 period = 月初）
    periods_seen = []
    for item in data["items"]:
        p = item["period"]
        idx = item["periodIndex"]
        if p not in [x[0] for x in periods_seen]:
            periods_seen.append((p, idx))
    assert periods_seen[0] == ("2026-01-01", 1)
    assert periods_seen[1] == ("2026-02-01", 2)


async def test_carbon_stats_actual_excludes_planned(
    client: AsyncClient,
    project: Project,
    resources: list[Resource],
    usage_records: list[TaskResourceUsage],
):
    """关键不变量：ACTUAL 聚合严格不包含 PLANNED 行。"""
    r1_id = resources[0].id
    r2_id = resources[1].id
    assert r1_id is not None
    assert r2_id is not None

    resp_actual = await client.get(
        f"/projects/{project.id}/resource-usage/stats/carbon?usageType=ACTUAL"
    )
    assert resp_actual.status_code == 200
    actual = resp_actual.json()
    actual_total = sum(item["emission"] for item in actual["items"])
    assert actual_total == pytest.approx(76.5)
    assert len(actual["items"]) == 3

    resp_planned = await client.get(
        f"/projects/{project.id}/resource-usage/stats/carbon?usageType=PLANNED"
    )
    assert resp_planned.status_code == 200
    planned = resp_planned.json()
    planned_total = sum(item["emission"] for item in planned["items"])
    assert planned_total == pytest.approx(274.5)
    assert len(planned["items"]) == 2

    actual_keys = {(i["period"], i["resourceId"]) for i in actual["items"]}
    planned_keys = {(i["period"], i["resourceId"]) for i in planned["items"]}
    assert ("2026-02-01", r2_id) in planned_keys
    assert ("2026-02-01", r2_id) not in actual_keys


async def test_carbon_stats_planned_month_reads_usage_only(
    client: AsyncClient,
    project: Project,
    usage_records: list[TaskResourceUsage],
):
    """PLANNED 一律只读 usage 表（无 source 字段，不走基线快照）。"""
    resp = await client.get(
        f"/projects/{project.id}/resource-usage/stats/carbon?usageType=PLANNED"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "source" not in data
    assert len(data["items"]) == 2
    total = sum(item["emission"] for item in data["items"])
    assert total == pytest.approx(274.5)


async def test_carbon_stats_planned_day_week_422(
    client: AsyncClient,
    project: Project,
    usage_records: list[TaskResourceUsage],
):
    """PLANNED 仅支持月粒度：granularity=day/week 返回 422。"""
    for gran in ("day", "week"):
        resp = await client.get(
            f"/projects/{project.id}/resource-usage/stats/carbon"
            f"?usageType=PLANNED&granularity={gran}"
        )
        assert resp.status_code == 422, resp.text


async def test_carbon_stats_invalid_granularity_422(
    client: AsyncClient,
    project: Project,
    usage_records: list[TaskResourceUsage],
):
    """非法 granularity → 422。"""
    resp = await client.get(
        f"/projects/{project.id}/resource-usage/stats/carbon"
        "?usageType=ACTUAL&granularity=year"
    )
    assert resp.status_code == 422


async def test_carbon_stats_date_window(
    client: AsyncClient,
    project: Project,
    resources: list[Resource],
    usage_records: list[TaskResourceUsage],
):
    """startDate/endDate 限定窗口：[2026-02-01, 2026-03-01) → 仅 Feb 资源。"""
    resp = await client.get(
        f"/projects/{project.id}/resource-usage/stats/carbon"
        "?usageType=ACTUAL&startDate=2026-02-01&endDate=2026-03-01"
    )
    assert resp.status_code == 200
    data = resp.json()
    # Feb: r1 ACTUAL(15) = 1 条（r2 PLANNED 已按 usageType 排除）
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == pytest.approx(15.0)


async def test_carbon_stats_end_exclusive(
    client: AsyncClient,
    project: Project,
    usage_records: list[TaskResourceUsage],
):
    """endDate 不含：窗口 [2026-02-01, 2026-02-05) 不含 Feb 5 的 ACTUAL。"""
    resp = await client.get(
        f"/projects/{project.id}/resource-usage/stats/carbon"
        "?usageType=ACTUAL&startDate=2026-02-01&endDate=2026-02-05"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []


async def test_carbon_stats_day_granularity(
    client: AsyncClient,
    project: Project,
    usage_records: list[TaskResourceUsage],
):
    """ACTUAL 日粒度：period 精确到日，逐日分组。"""
    resp = await client.get(
        f"/projects/{project.id}/resource-usage/stats/carbon"
        "?usageType=ACTUAL&granularity=day"
    )
    assert resp.status_code == 200
    data = resp.json()
    # 3 ACTUAL 行在不同日：Jan15 r1 / Jan10 r2 / Feb5 r1 → 3 个 period
    assert data["totalPeriods"] == 3
    assert len(data["items"]) == 3
    periods = {item["period"] for item in data["items"]}
    assert periods == {"2026-01-10", "2026-01-15", "2026-02-05"}
    total = sum(item["emission"] for item in data["items"])
    assert total == pytest.approx(76.5)


async def test_carbon_stats_empty_project(client: AsyncClient, project: Project):
    """无 usage_records fixture → 空响应。"""
    resp = await client.get(
        f"/projects/{project.id}/resource-usage/stats/carbon?usageType=ACTUAL"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["totalPeriods"] == 0
    assert data["totalResources"] == 0


async def test_carbon_stats_unknown_project_404(client: AsyncClient):
    """GET 不存在的 project_id → 404。"""
    resp = await client.get(
        "/projects/9999/resource-usage/stats/carbon?usageType=ACTUAL"
    )
    assert resp.status_code == 404
