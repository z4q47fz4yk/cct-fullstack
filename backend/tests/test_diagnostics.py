"""数据体检端点测试（GET /projects/{id}/diagnostics/resources）。

覆盖：
- ZERO_FACTOR / NEGATIVE_FACTOR / ZERO_PRICE 标志判定
- 无使用记录的资源完全不出现在结果中（用量驱动豁免）
- usage_type 口径过滤（ACTUAL/PLANNED 塌缩）
- 排序：ZERO_FACTOR 警告优先
- 项目隔离：他项目用量不串
"""

# pyright: reportCallIssue=false
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.task import Task
from src.schemas.diagnostics import DiagnosticFlag
from src.schemas.resource import ResourceCategory

# ============================================================
# Fixtures
# ============================================================


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    """主测试项目 A（自增 id，避免与种子数据冲突）。"""
    p = Project(name="诊断体检项目A", is_active=True)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def project_b(db_session: AsyncSession) -> Project:
    """隔离对照项目 B。"""
    p = Project(name="诊断体检项目B", is_active=True)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def tasks(
    db_session: AsyncSession, project: Project, project_b: Project
) -> dict[str, Task]:
    """A/B 各一条工序（用量 FK 需要）。"""
    out: dict[str, Task] = {}
    for key, proj in (("a", project), ("b", project_b)):
        pid = proj.id
        assert pid is not None
        t = Task(
            project_id=pid, code=f"DX-{key.upper()}", name="体检工序", duration=5.0
        )
        db_session.add(t)
        await db_session.commit()
        await db_session.refresh(t)
        out[key] = t
    return out


@pytest_asyncio.fixture
async def resources(
    db_session: AsyncSession, project: Project, project_b: Project
) -> dict[str, Resource]:
    """项目 A 的诊断场景资源 + 项目 B 的同名对照资源。

    - zero:  因子 0、有 ACTUAL+PLANNED 用量      → ZERO_FACTOR
    - pv:    因子 -5（碳汇）、仅有 ACTUAL 用量    → NEGATIVE_FACTOR
    - free:  单价 0、因子正常、仅有 PLANNED 用量  → ZERO_PRICE
    - ok:    各项正常、有用量                    → 无标志
    - idle:  因子 0 但无任何用量                  → 不出现在结果中
    - b_zero: 项目 B 的 0 因子资源（有用量，用于隔离断言）
    """
    pid_a = project.id
    pid_b = project_b.id
    assert pid_a is not None and pid_b is not None

    def make(pid: int, name: str, **kw) -> Resource:
        return Resource(project_id=pid, name=name, description="d", **kw)

    rs = [
        make(
            pid_a,
            "泥工",
            category=ResourceCategory.labor,
            unit="工日",
            unit_price=100.0,
            carbon_factor=0.0,
        ),
        make(
            pid_a,
            "光伏发电",
            category=ResourceCategory.others,
            unit="kWh",
            unit_price=50.0,
            carbon_factor=-5.0,
        ),
        make(
            pid_a,
            "免费水",
            category=ResourceCategory.material,
            unit="m³",
            unit_price=0.0,
            carbon_factor=3.0,
        ),
        make(
            pid_a,
            "正常机械",
            category=ResourceCategory.machinery,
            unit="台班",
            unit_price=120.0,
            carbon_factor=8.0,
        ),
        make(
            pid_a,
            "未使用资源",
            category=ResourceCategory.labor,
            unit="工日",
            unit_price=10.0,
            carbon_factor=0.0,
        ),
        make(
            pid_b,
            "泥工",
            category=ResourceCategory.labor,
            unit="工日",
            unit_price=100.0,
            carbon_factor=0.0,
        ),
    ]
    db_session.add_all(rs)
    await db_session.commit()
    for r in rs:
        await db_session.refresh(r)
    a_zero, pv, free, ok, idle, b_zero = rs
    return {
        "zero": a_zero,
        "a_zero": a_zero,
        "pv": pv,
        "free": free,
        "ok": ok,
        "idle": idle,
        "b_zero": b_zero,
    }


@pytest_asyncio.fixture
async def usages(
    db_session: AsyncSession,
    project: Project,
    project_b: Project,
    tasks: dict[str, Task],
    resources: dict[str, Resource],
) -> None:
    """混合口径的用量记录（数量与日期精确可验证）。"""
    pid_a = project.id
    assert pid_a is not None
    pid_b = project_b.id
    assert pid_b is not None
    tid_a = tasks["a"].id
    assert tid_a is not None
    tid_b = tasks["b"].id
    assert tid_b is not None

    def rid(key: str):
        r = resources[key]
        assert r.id is not None
        return r.id

    rows = [
        # zero：ACTUAL 3 + PLANNED 2，最近日期 d2
        TaskResourceUsage(
            project_id=pid_a,
            task_id=tid_a,
            resource_id=rid("a_zero"),
            usage_date=date(2026, 1, 10),
            quantity=3.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid_a,
            task_id=tid_a,
            resource_id=rid("a_zero"),
            usage_date=date(2026, 1, 20),
            quantity=2.0,
            usage_type=UsageType.PLANNED,
        ),
        # pv：仅 ACTUAL 4
        TaskResourceUsage(
            project_id=pid_a,
            task_id=tid_a,
            resource_id=rid("pv"),
            usage_date=date(2026, 1, 15),
            quantity=4.0,
            usage_type=UsageType.ACTUAL,
        ),
        # free：仅 PLANNED 7
        TaskResourceUsage(
            project_id=pid_a,
            task_id=tid_a,
            resource_id=rid("free"),
            usage_date=date(2026, 2, 1),
            quantity=7.0,
            usage_type=UsageType.PLANNED,
        ),
        # ok：ACTUAL 1 + PLANNED 1
        TaskResourceUsage(
            project_id=pid_a,
            task_id=tid_a,
            resource_id=rid("ok"),
            usage_date=date(2026, 1, 5),
            quantity=1.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid_a,
            task_id=tid_a,
            resource_id=rid("ok"),
            usage_date=date(2026, 1, 6),
            quantity=1.0,
            usage_type=UsageType.PLANNED,
        ),
        # planned_only 场景由 free 承担；idle 无任何用量
        # 项目 B：同名资源大额用量，用于隔离断言
        TaskResourceUsage(
            project_id=pid_b,
            task_id=tid_b,
            resource_id=rid("b_zero"),
            usage_date=date(2026, 3, 1),
            quantity=100.0,
            usage_type=UsageType.ACTUAL,
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()


# ============================================================
# 辅助
# ============================================================


def _by_name(items: list[dict], name: str) -> dict | None:
    return next((it for it in items if it["name"] == name), None)


# ============================================================
# 用例
# ============================================================


async def test_flags_exclusion_and_quantities(
    client: AsyncClient, project: Project, usages: None
):
    """标志判定正确；无用量资源不出现；数量与最近日期准确。"""
    pid = project.id
    resp = await client.get(f"/projects/{pid}/diagnostics/resources")
    assert resp.status_code == 200
    items = resp.json()["items"]
    names = {it["name"] for it in items}
    assert names == {"泥工", "光伏发电", "免费水", "正常机械"}

    zero = _by_name(items, "泥工")
    assert zero is not None
    assert zero["flags"] == [DiagnosticFlag.ZERO_FACTOR]
    assert zero["actualQuantity"] == pytest.approx(3.0)
    assert zero["plannedQuantity"] == pytest.approx(2.0)
    assert zero["lastUsageDate"] == "2026-01-20"

    pv = _by_name(items, "光伏发电")
    assert pv is not None
    assert pv["flags"] == [DiagnosticFlag.NEGATIVE_FACTOR]

    free = _by_name(items, "免费水")
    assert free is not None
    assert free["flags"] == [DiagnosticFlag.ZERO_PRICE]
    assert free["actualQuantity"] == 0.0

    ok = _by_name(items, "正常机械")
    assert ok is not None
    assert ok["flags"] == []


async def test_zero_factor_sorts_first(
    client: AsyncClient, project: Project, usages: None
):
    """ZERO_FACTOR（warning）排在 info 类之前。"""
    pid = project.id
    resp = await client.get(f"/projects/{pid}/diagnostics/resources")
    items = resp.json()["items"]
    flagged = [it for it in items if it["flags"]]
    assert flagged[0]["flags"] == [DiagnosticFlag.ZERO_FACTOR]


async def test_usage_type_filter_collapses(
    client: AsyncClient, project: Project, usages: None
):
    """ACTUAL 口径下：PLANNED-only 资源消失、planned 列恒为 0。"""
    pid = project.id
    resp = await client.get(f"/projects/{pid}/diagnostics/resources?usage_type=ACTUAL")
    assert resp.status_code == 200
    items = resp.json()["items"]
    names = {it["name"] for it in items}
    # 免费水只有 PLANNED 记录 → ACTUAL 口径下不存在
    assert "免费水" not in names
    zero = _by_name(items, "泥工")
    assert zero is not None
    assert zero["actualQuantity"] == pytest.approx(3.0)
    assert zero["plannedQuantity"] == 0.0

    resp_p = await client.get(
        f"/projects/{pid}/diagnostics/resources?usage_type=PLANNED"
    )
    items_p = resp_p.json()["items"]
    free = _by_name(items_p, "免费水")
    assert free is not None
    assert free["plannedQuantity"] == pytest.approx(7.0)


async def test_project_isolation(
    client: AsyncClient, project: Project, project_b: Project, usages: None
):
    """他项目的同名资源用量互不影响。"""
    resp_a = await client.get(f"/projects/{project.id}/diagnostics/resources")
    a_zero = _by_name(resp_a.json()["items"], "泥工")
    assert a_zero is not None
    assert a_zero["actualQuantity"] == pytest.approx(3.0)  # 不含 B 的 100

    resp_b = await client.get(f"/projects/{project_b.id}/diagnostics/resources")
    items_b = resp_b.json()["items"]
    assert len(items_b) == 1
    assert items_b[0]["name"] == "泥工"
    assert items_b[0]["actualQuantity"] == pytest.approx(100.0)


async def test_invalid_usage_type_rejected(
    client: AsyncClient, project: Project, usages: None
):
    """非法口径参数返回 422。"""
    resp = await client.get(
        f"/projects/{project.id}/diagnostics/resources?usage_type=WHATEVER"
    )
    assert resp.status_code == 422
