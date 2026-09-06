"""项目级逐日进度时间线端点测试。

覆盖 GET /projects/{project_id}/task/progress/timeline：
- 返回全部工序（含无进度记录者，空 series）
- 每日取最后一条（同日纠错语义），series 按日期升序
- actual_start_date / actual_completion_date / current_percent 汇总正确
- 跨项目隔离（空项目 / 不存在项目）
"""
# pyright: reportCallIssue=false

from datetime import date

import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project
from src.models.task import Task


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(name="Timeline Project", is_active=True)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def tasks(db_session: AsyncSession, project: Project) -> list[Task]:
    pid = project.id
    assert pid is not None
    ts = [
        Task(project_id=pid, code="T-A", name="工序A", duration=5.0),
        Task(project_id=pid, code="T-B", name="工序B", duration=3.0),
        Task(project_id=pid, code="T-C", name="工序C", duration=2.0),  # 无进度
    ]
    db_session.add_all(ts)
    await db_session.commit()
    for t in ts:
        await db_session.refresh(t)
    return ts


async def test_timeline_returns_all_tasks_empty_series(
    client: AsyncClient, project: Project, tasks: list[Task]
):
    """无任何进度记录：全部工序返回，series 均为空，汇总为零值。"""
    resp = await client.get(f"/projects/{project.id}/task/progress/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 3
    for item in data["items"]:
        assert item["series"] == []
        assert item["currentPercent"] == 0.0
        assert item["isCompleted"] is False
        assert item["actualStartDate"] is None
    # 按 code 升序（T-A, T-B, T-C）
    assert [i["taskCode"] for i in data["items"]] == ["T-A", "T-B", "T-C"]


async def test_timeline_daily_latest_and_series_order(
    client: AsyncClient,
    project: Project,
    tasks: list[Task],
    db_session: AsyncSession,
):
    """同日多记录取最后一条；series 按日期升序；跨工序互不干扰。"""
    pid = project.id
    t_a = tasks[0].id
    t_b = tasks[1].id
    assert pid is not None and t_a is not None and t_b is not None

    from src.models.progress import TaskProgress

    rows = [
        TaskProgress(project_id=pid, task_id=t_a, date=date(2026, 1, 5), percent=40.0),
        # 同日纠错：同日第二条覆盖第一条 → 该日累计 60
        TaskProgress(project_id=pid, task_id=t_a, date=date(2026, 1, 5), percent=60.0),
        TaskProgress(project_id=pid, task_id=t_a, date=date(2026, 1, 6), percent=80.0),
        TaskProgress(project_id=pid, task_id=t_a, date=date(2026, 1, 7), percent=100.0),
        TaskProgress(project_id=pid, task_id=t_b, date=date(2026, 1, 6), percent=30.0),
        TaskProgress(project_id=pid, task_id=t_b, date=date(2026, 1, 8), percent=70.0),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    resp = await client.get(f"/projects/{pid}/task/progress/timeline")
    assert resp.status_code == 200
    data = resp.json()
    by_code = {i["taskCode"]: i for i in data["items"]}

    a = by_code["T-A"]
    assert [p["date"] for p in a["series"]] == [
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
    ]
    assert [p["percent"] for p in a["series"]] == [60.0, 80.0, 100.0]  # 1/5 取 60
    assert a["actualStartDate"] == "2026-01-05"
    assert a["actualCompletionDate"] == "2026-01-07"
    assert a["currentPercent"] == 100.0
    assert a["isCompleted"] is True

    b = by_code["T-B"]
    assert [p["date"] for p in b["series"]] == ["2026-01-06", "2026-01-08"]
    assert [p["percent"] for p in b["series"]] == [30.0, 70.0]
    assert b["currentPercent"] == 70.0
    assert b["isCompleted"] is False
    assert b["actualCompletionDate"] is None

    c = by_code["T-C"]
    assert c["series"] == []
    assert c["currentPercent"] == 0.0


async def test_timeline_correction_after_completion(
    client: AsyncClient,
    project: Project,
    tasks: list[Task],
    db_session: AsyncSession,
):
    """100% 之后纠错改小：completion 置空、isCompleted=False、series 反映最新。"""
    pid = project.id
    t_a = tasks[0].id
    assert pid is not None and t_a is not None

    from src.models.progress import TaskProgress

    db_session.add_all([
        TaskProgress(project_id=pid, task_id=t_a, date=date(2026, 1, 5), percent=100.0),
        TaskProgress(project_id=pid, task_id=t_a, date=date(2026, 1, 6), percent=70.0),
    ])
    await db_session.commit()

    resp = await client.get(f"/projects/{pid}/task/progress/timeline")
    data = resp.json()
    item = data["items"][0]
    assert item["currentPercent"] == 70.0
    assert item["isCompleted"] is False
    assert item["actualCompletionDate"] is None
    assert [p["percent"] for p in item["series"]] == [100.0, 70.0]


async def test_timeline_project_isolated_and_404(
    client: AsyncClient,
    project: Project,
    tasks: list[Task],
    db_session: AsyncSession,
):
    """空项目返回空 items；不存在项目 404（CurrentProject 校验）。"""
    pid = project.id
    assert pid is not None

    # 另一项目，无 task
    other = Project(name="Other", is_active=True)
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    oid = other.id
    assert oid is not None

    resp = await client.get(f"/projects/{oid}/task/progress/timeline")
    assert resp.status_code == 200
    assert resp.json()["items"] == []

    # 该端点为项目内 task 前缀；不存在项目 → 404（由 CurrentProject 决定）
    resp = await client.get("/projects/999999/task/progress/timeline")
    assert resp.status_code == 404
