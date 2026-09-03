"""跨项目越权防护回归测试。

验证所有按 id 取实体的端点都做了项目隔离：
他项目的实体与"不存在"返回一致的 404/400，且数据不被改动。

背景：审查发现 get_task / get_resource / 优化结果 / 日报批次等
按主键直接 session.get，未校验 project_id 归属，存在跨项目读写风险。
"""

import uuid
from datetime import date

from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.daily_report import ImportBatch, ImportBatchStatus
from src.models.optimize import OptimizationRun, ParetoSolution
from src.models.project import Project
from src.models.resource import Resource, ResourceCategory
from src.models.task import Task
from src.schemas.optimize import RunStatusEnum

# 默认项目（由迁移 seed）
PID_A = 1

# 固定高位 id，避免与并行 worker 的普通测试数据冲突（嵌套事务回滚隔离）
TASK_A_ID = 987_001
RESOURCE_A_ID = 987_002


async def _seed(db_session: AsyncSession):
    """项目 A 内造任务/资源/优化运行+解/日报批次；另建项目 B。"""
    task_a = Task(
        id=TASK_A_ID,
        project_id=PID_A,
        code="ISO-TASK-A",
        name="项目A的任务",
        duration=5.0,
        completed=0.0,
    )
    resource_a = Resource(
        id=RESOURCE_A_ID,
        project_id=PID_A,
        name="隔离测试资源A",
        description="隔离测试",
        category=ResourceCategory.machinery,
        unit="台班",
        unit_price=100.0,
        carbon_factor=10.0,
    )
    run_a = OptimizationRun(
        project_id=PID_A,
        name="隔离测试运行",
        task_snapshot=[],
        dependency_snapshot=[],
        status=RunStatusEnum.SUCCESS,
    )
    solution_a = ParetoSolution(
        run_id=run_a.id,
        cost=1.0,
        emission=2.0,
        duration=3.0,
    )
    batch_a = ImportBatch(
        original_filename="隔离测试日报.xlsx",
        usage_date=date(2026, 1, 1),
        total_rows=0,
        status=ImportBatchStatus.ALLOCATING,
        project_id=PID_A,
    )
    project_b = Project(
        id=987_100,
        name="越权测试-项目B",
        description="隔离测试用",
        is_active=True,
    )

    db_session.add_all([task_a, resource_a, run_a, solution_a, batch_a, project_b])
    await db_session.commit()
    return {
        "task": task_a,
        "resource": resource_a,
        "run": run_a,
        "batch": batch_a,
        "project_b": project_b,
    }


# ---------------------------------------------------------------------------
# 任务
# ---------------------------------------------------------------------------


async def test_get_foreign_task_returns_404(client: AsyncClient, db_session):
    data = await _seed(db_session)
    resp = await client.get(f"/projects/{data['project_b'].id}/task/{TASK_A_ID}")
    assert resp.status_code == 404


async def test_update_foreign_task_rejected_and_untouched(
    client: AsyncClient, db_session
):
    data = await _seed(db_session)
    b_id = data["project_b"].id

    resp = await client.put(f"/projects/{b_id}/task/{TASK_A_ID}", json={"duration": 99})
    assert resp.status_code == 404

    # 项目 A 内原数据未被改动
    own = await client.get(f"/projects/{PID_A}/task/{TASK_A_ID}")
    assert own.status_code == 200
    assert own.json()["duration"] == 5.0


async def test_delete_foreign_task_rejected_and_kept(client: AsyncClient, db_session):
    data = await _seed(db_session)
    b_id = data["project_b"].id

    resp = await client.delete(f"/projects/{b_id}/task/{TASK_A_ID}")
    assert resp.status_code == 404

    own = await client.get(f"/projects/{PID_A}/task/{TASK_A_ID}")
    assert own.status_code == 200


async def test_predecessor_routes_blocked_for_foreign_task(
    client: AsyncClient, db_session
):
    data = await _seed(db_session)
    b_id = data["project_b"].id
    base = f"/projects/{b_id}/task/{TASK_A_ID}"

    # 任务归属校验先于依赖行查询：统一 404"任务不存在"
    resp_del = await client.delete(f"{base}/predecessors/1")
    assert resp_del.status_code == 404
    assert "任务不存在" in resp_del.json()["detail"]

    resp_put = await client.put(f"{base}/predecessors/1", json={"lag": 3})
    assert resp_put.status_code == 404
    assert "任务不存在" in resp_put.json()["detail"]

    resp_avail = await client.get(f"{base}/available-predecessors")
    assert resp_avail.status_code == 404


async def test_own_task_still_accessible(client: AsyncClient, db_session):
    await _seed(db_session)
    resp = await client.get(f"/projects/{PID_A}/task/{TASK_A_ID}")
    assert resp.status_code == 200
    assert resp.json()["code"] == "ISO-TASK-A"


# ---------------------------------------------------------------------------
# 资源
# ---------------------------------------------------------------------------


async def test_get_foreign_resource_returns_404(client: AsyncClient, db_session):
    data = await _seed(db_session)
    resp = await client.get(
        f"/projects/{data['project_b'].id}/resource/{RESOURCE_A_ID}"
    )
    assert resp.status_code == 404


async def test_update_foreign_resource_rejected_and_untouched(
    client: AsyncClient, db_session
):
    data = await _seed(db_session)
    b_id = data["project_b"].id

    resp = await client.put(
        f"/projects/{b_id}/resource/{RESOURCE_A_ID}", json={"unit_price": 1.0}
    )
    assert resp.status_code == 404

    own = await client.get(f"/projects/{PID_A}/resource/{RESOURCE_A_ID}")
    assert own.status_code == 200
    assert own.json()["unitPrice"] == 100.0


async def test_delete_foreign_resource_rejected_and_kept(
    client: AsyncClient, db_session
):
    data = await _seed(db_session)
    b_id = data["project_b"].id

    resp = await client.delete(f"/projects/{b_id}/resource/{RESOURCE_A_ID}")
    assert resp.status_code == 404

    own = await client.get(f"/projects/{PID_A}/resource/{RESOURCE_A_ID}")
    assert own.status_code == 200


# ---------------------------------------------------------------------------
# 优化结果
# ---------------------------------------------------------------------------


async def test_optimize_result_cross_project_returns_404(
    client: AsyncClient, db_session
):
    data = await _seed(db_session)
    run_id = data["run"].id
    assert isinstance(run_id, uuid.UUID)

    resp = await client.get(
        f"/projects/{data['project_b'].id}/optimize/{run_id}/result"
    )
    assert resp.status_code == 404

    # 正向：所属项目可正常读取
    own = await client.get(f"/projects/{PID_A}/optimize/{run_id}/result")
    assert own.status_code == 200
    assert own.json()["total"] >= 1


# ---------------------------------------------------------------------------
# 日报批次
# ---------------------------------------------------------------------------


async def test_daily_report_batch_cross_project_rejected(
    client: AsyncClient, db_session
):
    data = await _seed(db_session)
    b_id = data["project_b"].id
    batch_id = data["batch"].id

    # allocate：他项目批次 → 与"不存在"一致的业务错误（router 映射 400）
    resp_alloc = await client.post(
        f"/projects/{b_id}/daily-report/batches/{batch_id}/allocate", json=[]
    )
    assert resp_alloc.status_code == 400
    assert "不存在" in resp_alloc.json()["detail"]

    # submit：同样拒绝
    resp_submit = await client.post(
        f"/projects/{b_id}/daily-report/batches/{batch_id}/submit"
    )
    assert resp_submit.status_code == 400
    assert "不存在" in resp_submit.json()["detail"]


async def test_daily_report_batch_own_project_ok(client: AsyncClient, db_session):
    """正向对照：同批次在所属项目下可正常访问（空分配合法）。"""
    data = await _seed(db_session)
    batch_id = data["batch"].id

    resp = await client.post(
        f"/projects/{PID_A}/daily-report/batches/{batch_id}/allocate", json=[]
    )
    assert resp.status_code == 200
