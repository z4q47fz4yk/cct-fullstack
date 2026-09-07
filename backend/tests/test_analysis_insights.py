"""分析洞察三阶段改造后端测试：计划/施工/评价。"""
# pyright: reportCallIssue=false

from datetime import date
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.optimize import OptimizationRun, ParetoSolution, RunStatusEnum
from src.models.plan import Plan
from src.models.project import Project, ProjectStatus
from src.models.resource import Resource, ResourceCategory
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.tag import ResourceTag, Tag
from src.models.task import Task, TaskDependency
from src.schemas.optimize import TaskSnapshot, TaskStrategy
from src.schemas.task import DependencyType


@pytest_asyncio.fixture
async def insight_project(db_session: AsyncSession) -> dict:
    """项目 + 工序 + 资源 + 计划/实际用量 + 水电指定 的完整测试数据。"""
    project = Project(
        name="insight-project",
        description="分析洞察测试",
        planned_start_date=date(2026, 1, 1),
        status=ProjectStatus.CONSTRUCTION,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    pid = project.id
    assert pid is not None

    resources = [
        Resource(
            project_id=pid,
            name="材料A",
            description="d",
            category=ResourceCategory.material,
            unit_price=100.0,
            carbon_factor=50.0,
        ),
        Resource(
            project_id=pid,
            name="人工",
            description="d",
            category=ResourceCategory.labor,
            unit_price=200.0,
            carbon_factor=2.5,
        ),
        Resource(
            project_id=pid,
            name="人员生活",
            description="d",
            category=ResourceCategory.labor,
            unit_price=0.0,
            carbon_factor=2.0,
        ),
        Resource(
            project_id=pid,
            name="外购水",
            description="d",
            category=ResourceCategory.material,
            unit_price=5.0,
            carbon_factor=1.0,
        ),
        Resource(
            project_id=pid,
            name="光伏",
            description="d",
            category=ResourceCategory.material,
            unit_price=0.0,
            carbon_factor=-10.0,
        ),
        Resource(
            project_id=pid,
            name="旧设备",
            description="d",
            category=ResourceCategory.material,
            unit_price=30.0,
            carbon_factor=20.0,
        ),
        Resource(
            project_id=pid,
            name="新设备",
            description="d",
            category=ResourceCategory.material,
            unit_price=40.0,
            carbon_factor=5.0,
        ),
    ]
    db_session.add_all(resources)
    await db_session.commit()
    for r in resources:
        await db_session.refresh(r)

    t1 = Task(project_id=pid, code="T-1", name="工序一", duration=5.0)
    t2 = Task(project_id=pid, code="T-2", name="工序二", duration=3.0)
    db_session.add_all([t1, t2])
    await db_session.commit()
    await db_session.refresh(t1)
    await db_session.refresh(t2)
    t1_id, t2_id = cast(int, t1.id), cast(int, t2.id)
    db_session.add(
        TaskDependency(
            project_id=pid,
            task_id=t2_id,
            predecessor_id=t1_id,
            type=DependencyType.FS,
        )
    )

    r = {res.name: cast(int, res.id) for res in resources}
    usages = [
        TaskResourceUsage(
            project_id=pid,
            task_id=t1_id,
            resource_id=r["材料A"],
            usage_date=date(2026, 1, 2),
            quantity=10.0,
            usage_type=UsageType.PLANNED,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=t2_id,
            resource_id=r["人工"],
            usage_date=date(2026, 1, 6),
            quantity=20.0,
            usage_type=UsageType.PLANNED,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=t1_id,
            resource_id=r["旧设备"],
            usage_date=date(2026, 1, 2),
            quantity=8.0,
            usage_type=UsageType.PLANNED,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=t1_id,
            resource_id=r["新设备"],
            usage_date=date(2026, 1, 2),
            quantity=6.0,
            usage_type=UsageType.PLANNED,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=t1_id,
            resource_id=r["光伏"],
            usage_date=date(2026, 1, 2),
            quantity=2.0,
            usage_type=UsageType.PLANNED,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=t1_id,
            resource_id=r["外购水"],
            usage_date=date(2026, 1, 2),
            quantity=3.0,
            usage_type=UsageType.PLANNED,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=t1_id,
            resource_id=r["材料A"],
            usage_date=date(2026, 1, 3),
            quantity=12.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=t1_id,
            resource_id=r["外购水"],
            usage_date=date(2026, 1, 3),
            quantity=3.0,
            usage_type=UsageType.ACTUAL,
        ),
    ]
    db_session.add_all(usages)
    project.water_resource_id = r["外购水"]
    db_session.add(project)
    await db_session.commit()

    return {
        "pid": pid,
        "t1": t1_id,
        "t2": t2_id,
        "resource_ids": r,
    }


async def test_project_status_and_water_fields(client: AsyncClient, insight_project):
    """项目 status/水电字段 CRUD 与 is_active 同步。"""
    pid = insight_project["pid"]
    resp = await client.post(
        "/project",
        json={"name": "planning-proj", "description": "d", "status": "PLANNING"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "PLANNING"
    assert data["is_active"] is False
    new_id = data["id"]

    resp = await client.put(f"/project/{new_id}", json={"is_active": True})
    assert resp.json()["status"] == "CONSTRUCTION"

    resp = await client.put(f"/project/{new_id}", json={"status": "COMPLETED"})
    assert resp.json()["is_active"] is False

    water_id = insight_project["resource_ids"]["外购水"]
    resp = await client.put(f"/project/{pid}", json={"water_resource_id": water_id})
    assert resp.status_code == 200
    assert resp.json()["water_resource_id"] == water_id
    resp = await client.put(f"/project/{pid}", json={"water_resource_id": None})
    assert resp.json()["water_resource_id"] is None


async def test_weather_crud(client: AsyncClient, insight_project):
    """天气月度记录 CRUD。"""
    pid = insight_project["pid"]
    resp = await client.post(
        f"/projects/{pid}/weather",
        json={
            "month": "2026-01-01",
            "precipitationMm": 12.5,
            "temperatureC": 3.2,
            "sunshineHours": 4.0,
        },
    )
    assert resp.status_code == 201
    record = resp.json()
    assert record["month"] == "2026-01-01"

    resp = await client.post(
        f"/projects/{pid}/weather",
        json={"month": "2026-01-01", "precipitationMm": 1.0},
    )
    assert resp.status_code == 409

    resp = await client.post(
        f"/projects/{pid}/weather",
        json={"month": "2026-02-15"},
    )
    assert resp.status_code == 422

    resp = await client.put(
        f"/projects/{pid}/weather/{record['id']}", json={"temperatureC": None}
    )
    assert resp.status_code == 200
    assert resp.json()["temperatureC"] is None

    resp = await client.delete(f"/projects/{pid}/weather/{record['id']}")
    assert resp.status_code == 204


async def test_progress_crud_sync_and_correction(
    client: AsyncClient, insight_project, db_session: AsyncSession
):
    """进度录入 append-only、Task.completed 同步、纠错语义。"""
    pid = insight_project["pid"]
    t1 = insight_project["t1"]
    t2 = insight_project["t2"]

    resp = await client.post(
        f"/projects/{pid}/task/{t1}/progress",
        json={"date": "2026-01-05", "percent": 40},
    )
    assert resp.status_code == 201

    resp = await client.post(
        f"/projects/{pid}/task/{t1}/progress",
        json={"date": "2026-01-05", "percent": 60},
    )
    assert resp.status_code == 201

    resp = await client.post(
        f"/projects/{pid}/task/{t1}/progress",
        json={"date": "2026-01-06", "percent": 100},
    )
    assert resp.status_code == 201

    resp = await client.get(f"/projects/{pid}/task/{t1}/progress/summary")
    summary = resp.json()
    assert summary["currentPercent"] == 100
    assert summary["isCompleted"] is True
    assert summary["actualStartDate"] == "2026-01-05"
    assert summary["actualCompletionDate"] == "2026-01-06"
    assert summary["recordCount"] == 3

    task = await db_session.get(Task, t1)
    assert task is not None and task.completed == 1.0

    # 纠错：100% 之后改小，最新状态不再是完成
    resp = await client.post(
        f"/projects/{pid}/task/{t1}/progress",
        json={"date": "2026-01-07", "percent": 80},
    )
    assert resp.status_code == 201
    summary = (await client.get(f"/projects/{pid}/task/{t1}/progress/summary")).json()
    assert summary["isCompleted"] is False
    assert summary["actualCompletionDate"] is None

    # 批量录入（日报流程）
    resp = await client.post(
        f"/projects/{pid}/task/progress/batch",
        json={
            "items": [
                {"task_id": t1, "date": "2026-01-08", "percent": 100},
                {"task_id": t2, "date": "2026-01-09", "percent": 100},
            ]
        },
    )
    assert resp.status_code == 201
    task = await db_session.get(Task, t2)
    assert task is not None and task.completed == 1.0

    history = (await client.get(f"/projects/{pid}/task/{t1}/progress")).json()
    assert history["total"] == 5


async def test_plan_estimate_save_and_upsert(client: AsyncClient, insight_project):
    """计划估算、依赖冲突、保存与单行 upsert。"""
    pid = insight_project["pid"]

    resp = await client.get(f"/projects/{pid}/plans")
    assert resp.status_code == 404

    resp = await client.post(f"/projects/{pid}/plans/estimate", json={})
    assert resp.status_code == 200
    est = resp.json()
    assert est["totalDuration"] == 8
    assert len(est["tasks"]) == 2
    assert len(est["monthly"]) >= 1
    assert est["totalCost"] > 0
    assert est["totalEmission"] > 0

    # 显式 start 早于依赖约束 → 422
    resp = await client.post(
        f"/projects/{pid}/plans/estimate",
        json={"tasks": [{"taskId": insight_project["t2"], "start": 0}]},
    )
    assert resp.status_code == 422
    assert "早于依赖约束" in resp.json()["detail"]

    rid = insight_project["resource_ids"]
    save_body = {
        "tasks": [{"taskId": insight_project["t1"], "start": 0}],
        "measures": [
            {"kind": "ADD", "resourceIds": [rid["光伏"]]},
            {"kind": "REPLACE", "resourceIds": [rid["旧设备"], rid["新设备"]]},
        ],
    }
    resp = await client.post(f"/projects/{pid}/plans", json=save_body)
    assert resp.status_code == 201
    saved = resp.json()
    plan_id = saved["id"]
    assert saved["status"] == "PLANNED"
    assert len(saved["measures"]) == 2
    saving_by_kind = {m["kind"]: m["estimatedSaving"] for m in saved["measures"]}
    assert saving_by_kind["ADD"] == pytest.approx(20.0)
    assert saving_by_kind["REPLACE"] == pytest.approx(130.0)

    # 再次保存 → 同一行更新
    resp = await client.post(
        f"/projects/{pid}/plans",
        json={"tasks": [{"taskId": insight_project["t1"], "duration": 6.0}]},
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == plan_id
    assert resp.json()["totalDuration"] == 9

    resp = await client.get(f"/projects/{pid}/plans")
    assert resp.status_code == 200
    assert resp.json()["id"] == plan_id


async def test_plan_estimate_inherits_solution_strategy(
    client: AsyncClient, insight_project, db_session: AsyncSession
):
    """携带 sourceSolutionId 时，未列出的工序继承解的策略（mode/start）。"""
    pid = insight_project["pid"]
    t1 = insight_project["t1"]
    t2 = insight_project["t2"]
    run = OptimizationRun(
        id=uuid4(),
        project_id=pid,
        task_snapshot=[
            TaskSnapshot(id=t1, code="T-1", name="工序一", duration=5.0),
            TaskSnapshot(id=t2, code="T-2", name="工序二", duration=3.0),
        ],
        dependency_snapshot=[],
        pop_size=10,
        max_gen=1,
        irr=0.05,
        accelerated_ratio=0.8,
        max_offset=60,
        status=RunStatusEnum.SUCCESS,
    )
    db_session.add(run)
    await db_session.commit()
    solution = ParetoSolution(
        run_id=run.id,
        strategies=[
            TaskStrategy(task_id=t1, mode=1, start=0),
            TaskStrategy(task_id=t2, mode=2, start=6),
        ],
        cost=100.0,
        emission=10.0,
        duration=9.0,
        violations=[],
    )
    db_session.add(solution)
    await db_session.commit()
    await db_session.refresh(solution)

    resp = await client.post(
        f"/projects/{pid}/plans/estimate",
        json={"sourceSolutionId": solution.id},
    )
    assert resp.status_code == 200
    est = resp.json()
    by_id = {task["taskId"]: task for task in est["tasks"]}
    assert by_id[t1]["mode"] == 1
    assert by_id[t1]["start"] == 0
    assert by_id[t1]["duration"] == 4.0  # 5 × accelerated_ratio(0.8)
    assert by_id[t2]["mode"] == 2
    assert by_id[t2]["start"] == 6
    assert est["totalDuration"] == 9

    # 已列出的工序只覆盖给定字段，其余仍继承
    resp = await client.post(
        f"/projects/{pid}/plans/estimate",
        json={
            "sourceSolutionId": solution.id,
            "tasks": [{"taskId": t2, "start": 7}],
        },
    )
    assert resp.status_code == 200
    by_id = {task["taskId"]: task for task in resp.json()["tasks"]}
    assert by_id[t1]["mode"] == 1
    assert by_id[t2]["start"] == 7
    assert by_id[t2]["mode"] == 2


async def test_plan_draft_and_conflict(client: AsyncClient, insight_project):
    """保存草稿：DRAFT 状态；已有正式基线后 409。"""
    pid = insight_project["pid"]
    resp = await client.post(f"/projects/{pid}/plans/draft", json={})
    assert resp.status_code == 201
    assert resp.json()["status"] == "DRAFT"

    resp = await client.post(f"/projects/{pid}/plans", json={})
    assert resp.status_code == 201
    resp = await client.post(f"/projects/{pid}/plans/draft", json={})
    assert resp.status_code == 409


async def test_measure_validation_and_overlap(client: AsyncClient, insight_project):
    """措施资源校验与防重复计算。"""
    pid = insight_project["pid"]
    rid = insight_project["resource_ids"]

    # ADD 要求负因子
    resp = await client.post(
        f"/projects/{pid}/measures",
        json={"kind": "ADD", "resourceIds": [rid["材料A"]]},
    )
    assert resp.status_code == 422

    resp = await client.post(
        f"/projects/{pid}/measures",
        json={"kind": "ADD", "resourceIds": [rid["光伏"]]},
    )
    assert resp.status_code == 201
    assert resp.json()["estimatedSaving"] == pytest.approx(20.0)

    # 同一旧资源不能被第二个替换措施使用
    resp = await client.post(
        f"/projects/{pid}/measures",
        json={"kind": "REPLACE", "resourceIds": [rid["旧设备"], rid["新设备"]]},
    )
    assert resp.status_code == 201
    resp = await client.post(
        f"/projects/{pid}/measures",
        json={"kind": "REPLACE", "resourceIds": [rid["旧设备"], rid["光伏"]]},
    )
    assert resp.status_code == 422

    resp = await client.get(f"/projects/{pid}/measures")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_measure_actual_saving_implemented_date_window(
    client: AsyncClient, insight_project, db_session: AsyncSession
):
    """actualSaving 从 implementedDate 起算（实施日前的用量不计入）。"""
    pid = insight_project["pid"]
    pv_id = insight_project["resource_ids"]["光伏"]
    resp = await client.post(
        f"/projects/{pid}/measures",
        json={"kind": "ADD", "resourceIds": [pv_id]},
    )
    assert resp.status_code == 201
    measure_id = resp.json()["id"]

    db_session.add_all([
        TaskResourceUsage(
            project_id=pid,
            task_id=insight_project["t1"],
            resource_id=pv_id,
            usage_date=date(2026, 1, 2),
            quantity=3.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=insight_project["t1"],
            resource_id=pv_id,
            usage_date=date(2026, 1, 10),
            quantity=5.0,
            usage_type=UsageType.ACTUAL,
        ),
    ])
    await db_session.commit()

    resp = await client.put(
        f"/projects/{pid}/measures/{measure_id}",
        json={"implementedDate": "2026-01-05"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # 仅 1/10 的 5 单位计：-(5 × -10) = 50
    assert data["actualSaving"] == pytest.approx(50.0)
    assert data["savingDifference"] == pytest.approx(30.0)


async def test_carbon_stats_cost_bucket_and_negative_emission(
    client: AsyncClient, insight_project
):
    """碳排统计（/resource-usage/stats/carbon）：cost/水电桶/负因子资源。

    PLANNED 口径只读 usage 表（不读计划基线快照），负因子（光伏）在
    usage 现场聚合中允许负排放。
    """
    pid = insight_project["pid"]

    # ACTUAL：材料A(12×50=600) + 外购水(3×1=3，单价5 → cost 15)
    resp = await client.get(
        f"/projects/{pid}/resource-usage/stats/carbon?usageType=ACTUAL"
    )
    assert resp.status_code == 200
    actual_items = resp.json()["items"]
    assert all("cost" in item for item in actual_items)
    water_item = next(item for item in actual_items if item["bucket"] == "water")
    assert water_item["cost"] == pytest.approx(15.0)

    # PLANNED：一律读 usage 行（无 source 字段，与基线解耦）
    resp = await client.get(
        f"/projects/{pid}/resource-usage/stats/carbon?usageType=PLANNED"
    )
    assert resp.status_code == 200
    planned = resp.json()
    assert "source" not in planned

    # 保存基线不影响 PLANNED 口径（基线语义独立于碳排统计）
    await client.post(f"/projects/{pid}/plans", json={})
    resp = await client.get(
        f"/projects/{pid}/resource-usage/stats/carbon?usageType=PLANNED"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "source" not in data
    items = data["items"]
    assert len(items) >= 1
    assert all(item["period"] == "2026-01-01" for item in items)
    assert any(
        item["resourceId"] == insight_project["resource_ids"]["外购水"]
        for item in items
    )

    # 负因子资源在聚合中允许负排放（光伏 PLANNED 用量 2 × (-10) = -20）
    pv_item = next(
        item
        for item in items
        if item["resourceId"] == insight_project["resource_ids"]["光伏"]
    )
    assert pv_item["emission"] == pytest.approx(-20.0)


async def test_chart_pie_cost_metric(
    client: AsyncClient, insight_project, db_session: AsyncSession
):
    """饼图聚合支持 cost 指标（切片绑定普通标签 + 资源打标）。"""
    pid = insight_project["pid"]
    tag = Tag(project_id=pid, name="施工用材", group="材料", description="d")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    tag_id = cast(int, tag.id)
    db_session.add(
        ResourceTag(
            project_id=pid,
            resource_id=insight_project["resource_ids"]["材料A"],
            tag_id=tag_id,
        )
    )
    await db_session.commit()

    resp = await client.post(f"/projects/{pid}/chart", json={"name": "成本分布"})
    assert resp.status_code == 201
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/slices",
        json={"slices": [{"name": "施工用材", "tags": [{"tagId": tag_id}]}]},
    )
    assert resp.status_code == 200, resp.text
    # 手动刷新物化视图（fixture 数据在请求会话内可见）
    resp = await client.post(f"/projects/{pid}/usage-snapshot/refresh")
    assert resp.status_code == 200

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data?metric=cost")
    assert resp.status_code == 200
    assert resp.json()[0]["value"] == pytest.approx(1200.0)

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.json()[0]["value"] == pytest.approx(600.0)


async def test_compliance_with_and_without_baseline(
    client: AsyncClient, insight_project
):
    """计划践行度：无基线 409；有基线返回对照与解锁标志。"""
    pid = insight_project["pid"]
    resp = await client.get(f"/projects/{pid}/evaluation/compliance")
    assert resp.status_code == 409

    await client.post(f"/projects/{pid}/plans", json={})
    t1 = insight_project["t1"]
    t2 = insight_project["t2"]
    await client.post(
        f"/projects/{pid}/task/progress/batch",
        json={
            "items": [
                {"taskId": t1, "date": "2026-01-06", "percent": 100},
                {"taskId": t2, "date": "2026-01-09", "percent": 100},
            ]
        },
    )

    resp = await client.get(f"/projects/{pid}/evaluation/compliance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluationUnlocked"] is False
    assert data["plannedDuration"] == 8
    assert data["plannedCost"] > 0
    assert data["actualCost"] > 0
    assert len(data["taskRows"]) == 2
    assert len(data["monthly"]) >= 1
    assert len(data["materialDiffs"]) >= 1
    assert all(diff["resourceName"] != "人员生活" for diff in data["materialDiffs"])

    resp = await client.put(f"/project/{pid}", json={"status": "COMPLETED"})
    assert resp.status_code == 200
    data = (await client.get(f"/projects/{pid}/evaluation/compliance")).json()
    assert data["evaluationUnlocked"] is True
    assert data["projectCompleted"] is True


# ============================================================================
# 计划基线过期检查（B-4 修复：数据体检页手动触发，不监听业务变更）
# ============================================================================


async def _save_baseline(client: AsyncClient, pid: int) -> None:
    """保存一条简单基线（无措施、无任务调整）。"""
    resp = await client.post(f"/projects/{pid}/plans", json={})
    assert resp.status_code == 201
    assert resp.json()["isStale"] is False


async def test_plan_stale_flow(client: AsyncClient, insight_project):
    """保存→false；改任务工期后未体检仍 false；体检后 true；重存恢复 false。"""
    pid = insight_project["pid"]
    await _save_baseline(client, pid)

    resp = await client.get(f"/projects/{pid}/plans")
    assert resp.status_code == 200
    assert resp.json()["isStale"] is False

    # 改任务工期：未体检前 GET /plans 仍是存储值（无隐式更新、无额外查询）
    resp = await client.put(
        f"/projects/{pid}/task/{insight_project['t1']}", json={"duration": 6.0}
    )
    assert resp.status_code == 200
    resp = await client.get(f"/projects/{pid}/plans")
    assert resp.json()["isStale"] is False

    # 数据体检页手动触发 → 过期并落库
    resp = await client.get(f"/projects/{pid}/diagnostics/plan")
    assert resp.status_code == 200
    check = resp.json()
    assert check["hasPlan"] is True
    assert check["isStale"] is True
    assert check["planStatus"] == "PLANNED"
    assert check["checkedAt"] is not None

    # 落库后 GET /plans 读存储值
    resp = await client.get(f"/projects/{pid}/plans")
    assert resp.json()["isStale"] is True

    # 重新保存基线 → 恢复最新
    await _save_baseline(client, pid)
    resp = await client.get(f"/projects/{pid}/plans")
    assert resp.json()["isStale"] is False


async def test_plan_stale_after_dependency_change(
    client: AsyncClient, insight_project, db_session: AsyncSession
):
    """新增依赖后体检 → 过期。"""
    pid = insight_project["pid"]
    await _save_baseline(client, pid)
    db_session.add(
        TaskDependency(
            project_id=pid,
            task_id=insight_project["t1"],
            predecessor_id=insight_project["t2"],
            type=DependencyType.FF,
        )
    )
    await db_session.commit()
    resp = await client.get(f"/projects/{pid}/diagnostics/plan")
    assert resp.json()["isStale"] is True


async def test_plan_stale_after_resource_change(client: AsyncClient, insight_project):
    """改资源碳因子后体检 → 过期。"""
    pid = insight_project["pid"]
    await _save_baseline(client, pid)
    rid = insight_project["resource_ids"]["材料A"]
    resp = await client.put(
        f"/projects/{pid}/resource/{rid}", json={"carbon_factor": 99.0}
    )
    assert resp.status_code == 200
    resp = await client.get(f"/projects/{pid}/diagnostics/plan")
    assert resp.json()["isStale"] is True


async def test_plan_stale_after_planned_usage_change(
    client: AsyncClient, insight_project
):
    """新增 PLANNED 用量后体检 → 过期。"""
    pid = insight_project["pid"]
    await _save_baseline(client, pid)
    resp = await client.post(
        f"/projects/{pid}/resource-usage/batch",
        json={
            "name": "补录计划用量",
            "items": [
                {
                    "task_id": insight_project["t2"],
                    "resource_id": insight_project["resource_ids"]["材料A"],
                    "usage_date": "2026-01-08",
                    "quantity": 4.0,
                    "usage_type": "PLANNED",
                }
            ],
        },
    )
    assert resp.status_code == 201
    resp = await client.get(f"/projects/{pid}/diagnostics/plan")
    assert resp.json()["isStale"] is True


async def test_plan_stale_after_measure_change(client: AsyncClient, insight_project):
    """新增/修改低碳措施后体检 → 过期。"""
    pid = insight_project["pid"]
    rid = insight_project["resource_ids"]
    await _save_baseline(client, pid)

    # 直接经 measures API 新建措施（plan_id 为空），指纹变化 → 过期
    resp = await client.post(
        f"/projects/{pid}/measures",
        json={"kind": "ADD", "resourceIds": [rid["光伏"]]},
    )
    assert resp.status_code == 201
    resp = await client.get(f"/projects/{pid}/diagnostics/plan")
    assert resp.json()["isStale"] is True


async def test_plan_stale_actual_usage_not_flagged(
    client: AsyncClient, insight_project
):
    """ACTUAL 用量变化（日报导入场景）不触发过期——计划估算只读 PLANNED。"""
    pid = insight_project["pid"]
    await _save_baseline(client, pid)
    resp = await client.post(
        f"/projects/{pid}/resource-usage/batch",
        json={
            "name": "补录实际用量",
            "items": [
                {
                    "task_id": insight_project["t2"],
                    "resource_id": insight_project["resource_ids"]["材料A"],
                    "usage_date": "2026-01-09",
                    "quantity": 4.0,
                    "usage_type": "ACTUAL",
                }
            ],
        },
    )
    assert resp.status_code == 201
    resp = await client.get(f"/projects/{pid}/diagnostics/plan")
    assert resp.json()["isStale"] is False


async def test_plan_stale_no_plan(client: AsyncClient, insight_project):
    """无基线：has_plan=false，不落库。"""
    pid = insight_project["pid"]
    resp = await client.get(f"/projects/{pid}/diagnostics/plan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hasPlan"] is False
    assert data["isStale"] is None
    assert data["planStatus"] is None
    assert data["checkedAt"] is None


async def test_plan_stale_draft(client: AsyncClient, insight_project):
    """草稿同样参与过期检查。"""
    pid = insight_project["pid"]
    resp = await client.post(f"/projects/{pid}/plans/draft", json={})
    assert resp.status_code == 201
    assert resp.json()["isStale"] is False
    resp = await client.put(
        f"/projects/{pid}/task/{insight_project['t2']}", json={"duration": 4.0}
    )
    assert resp.status_code == 200
    resp = await client.get(f"/projects/{pid}/diagnostics/plan")
    check = resp.json()
    assert check["hasPlan"] is True
    assert check["planStatus"] == "DRAFT"
    assert check["isStale"] is True


async def test_plan_stale_legacy_without_fingerprint(
    client: AsyncClient, insight_project, db_session: AsyncSession
):
    """旧基线（data_fingerprint 为空）体检 → 判为过期。"""
    pid = insight_project["pid"]
    await _save_baseline(client, pid)
    plan = (await db_session.exec(select(Plan).where(Plan.project_id == pid))).first()
    assert plan is not None
    plan.data_fingerprint = None
    await db_session.commit()
    resp = await client.get(f"/projects/{pid}/diagnostics/plan")
    assert resp.json()["isStale"] is True
