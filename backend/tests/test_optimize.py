"""Optimize router 测试（不含后台 NSGA2 任务启动）。"""
# pyright: reportCallIssue=false

import uuid

import pytest
import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.optimize import (
    OptimizationRun,
    ParetoSolution,
    ResourceConstraint,
    RunStatusEnum,
)
from src.models.project import Project
from src.models.resource import Resource, ResourceCategory
from src.models.task import Task, TaskDependency
from src.schemas.optimize import DependencySnapshot, TaskSnapshot, TaskStrategy
from src.schemas.task import DependencyType

# 默认项目 id
PID = 1
OTHER_PID = 2

# 固定 UUID（便于参数化）
PENDING_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")
RUNNING_UUID = uuid.UUID("00000000-0000-0000-0000-000000000002")
SUCCESS_UUID = uuid.UUID("00000000-0000-0000-0000-000000000003")
FAILURE_UUID = uuid.UUID("00000000-0000-0000-0000-000000000004")
MISSING_UUID = uuid.UUID("00000000-0000-0000-0000-000000000099")


def _snapshots(
    task_ids: tuple[int, ...] = (1, 2),
) -> tuple[list[TaskSnapshot], list[DependencySnapshot]]:
    """构造默认任务/依赖快照（task 1 -> task 2，FS）。"""
    tasks = [
        TaskSnapshot(id=tid, code=f"T-{tid}", name=f"任务{tid}", duration=2.0)
        for tid in task_ids
    ]
    deps = [
        DependencySnapshot(
            task_id=task_ids[1],
            predecessor_id=task_ids[0],
            type=DependencyType.FS,
        )
    ]
    return tasks, deps


@pytest_asyncio.fixture
async def resources_for_optimize(db_session: AsyncSession):
    """插入 4 个 Resource（project_id=1），第 4 个用于 constraint 创建成功路径"""
    objs = [
        Resource(
            id=11001,
            project_id=PID,
            name="opt-r1",
            description="d1",
            category=ResourceCategory.machinery,
        ),
        Resource(
            id=10002,
            project_id=PID,
            name="opt-r2",
            description="d2",
            category=ResourceCategory.labor,
        ),
        Resource(
            id=10003,
            project_id=PID,
            name="opt-r3",
            description="d3",
            category=ResourceCategory.material,
        ),
        Resource(
            id=10004,
            project_id=PID,
            name="opt-r4",
            description="d4",
            category=ResourceCategory.machinery,
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


@pytest_asyncio.fixture
async def runs(db_session: AsyncSession):
    """插入 4 条 OptimizationRun（4 种状态）"""
    snap_tasks, snap_deps = _snapshots()
    objs = [
        OptimizationRun(
            id=PENDING_UUID,
            project_id=PID,
            name="串行 #1",
            task_snapshot=snap_tasks,
            dependency_snapshot=snap_deps,
            pop_size=50,
            max_gen=100,
            irr=0.05,
            accelerated_ratio=0.8,
            max_offset=60,
            curr_gen=0,
            status=RunStatusEnum.PENDING,
        ),
        OptimizationRun(
            id=RUNNING_UUID,
            project_id=PID,
            task_snapshot=snap_tasks,
            dependency_snapshot=snap_deps,
            pop_size=50,
            max_gen=100,
            irr=0.05,
            accelerated_ratio=0.8,
            max_offset=60,
            curr_gen=30,
            status=RunStatusEnum.RUNNING,
        ),
        OptimizationRun(
            id=SUCCESS_UUID,
            project_id=PID,
            name="并行 #2",
            task_snapshot=snap_tasks,
            dependency_snapshot=snap_deps,
            pop_size=50,
            max_gen=100,
            irr=0.05,
            accelerated_ratio=0.8,
            max_offset=60,
            curr_gen=100,
            status=RunStatusEnum.SUCCESS,
        ),
        OptimizationRun(
            id=FAILURE_UUID,
            project_id=PID,
            task_snapshot=snap_tasks,
            dependency_snapshot=snap_deps,
            pop_size=50,
            max_gen=100,
            irr=0.05,
            accelerated_ratio=0.8,
            max_offset=60,
            curr_gen=0,
            status=RunStatusEnum.FAILURE,
            error_msg="无可行解",
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


@pytest_asyncio.fixture
async def pareto_solutions(db_session: AsyncSession, runs):
    """为 SUCCESS_UUID 插入 2 条 ParetoSolution"""
    objs = [
        ParetoSolution(
            run_id=SUCCESS_UUID,
            strategies=[],
            cost=100.0,
            emission=50.0,
            duration=10.0,
            violations=[],
        ),
        ParetoSolution(
            run_id=SUCCESS_UUID,
            strategies=[],
            cost=200.0,
            emission=30.0,
            duration=15.0,
            violations=[],
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


@pytest_asyncio.fixture
async def constraints(db_session: AsyncSession, resources_for_optimize):
    """在 fixture 创建的资源（r1/r2/r3）上插入 3 条 ResourceConstraint"""
    r1, r2, r3, _ = resources_for_optimize
    objs = [
        ResourceConstraint(
            project_id=PID,
            resource_id=r1.id,
            max_usage=100.0,
            description="c1",
        ),
        ResourceConstraint(
            project_id=PID,
            resource_id=r2.id,
            max_usage=200.0,
            description="c2",
        ),
        ResourceConstraint(
            project_id=PID,
            resource_id=r3.id,
            max_usage=50.0,
            description="c3",
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    # refresh 让 id 字段被赋值
    for obj in objs:
        await db_session.refresh(obj)
    return objs


def _resource_ids(resources_for_optimize) -> dict[str, int]:
    """返回 r1/r2/r3/r4 -> 实际 resource.id 的映射，便于参数化"""
    return {f"r{i + 1}": r.id for i, r in enumerate(resources_for_optimize)}


def _constraint_ids(constraints) -> dict[str, int]:
    """返回各 constraint 的序号（1-based）-> constraint.id，便于参数化"""
    return {f"resource_{i + 1}": c.id for i, c in enumerate(constraints)}


def _url(pid: int = PID) -> str:
    return f"/projects/{pid}/optimize"


# =============================================================================
# 优化运行 CRUD
# =============================================================================


@pytest.mark.parametrize(
    "query, expected_total",
    [
        pytest.param("", 4, id="all"),
        pytest.param("page=1&per_page=2", 4, id="page1_per_page2"),
        pytest.param("page=3&per_page=2", 4, id="page3_last_page"),
        pytest.param("page=10&per_page=2", 4, id="empty_page"),
    ],
)
async def test_list_optimize(
    runs, client: AsyncClient, query: str, expected_total: int
):
    from urllib.parse import parse_qs

    params = parse_qs(query.lstrip("?")) if query else {}
    page = int(params.get("page", [1])[0])
    # 默认 per_page=10（参见 src/dependencies/public/pagination.py）
    per_page = int(params.get("per_page", [10])[0])
    expected_items = min(per_page, max(0, expected_total - (page - 1) * per_page))

    resp = await client.get(f"{_url()}?{query}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == expected_total
    assert len(data["items"]) == expected_items


@pytest.mark.parametrize(
    "run_id_str, code",
    [
        pytest.param(str(PENDING_UUID), 200, id="pending"),
        pytest.param(str(RUNNING_UUID), 200, id="running"),
        pytest.param(str(SUCCESS_UUID), 200, id="success"),
        pytest.param(str(FAILURE_UUID), 200, id="failure"),
        pytest.param(str(MISSING_UUID), 404, id="missing"),
    ],
)
async def test_get_running_status(
    runs, client: AsyncClient, run_id_str: str, code: int
):
    resp = await client.get(f"{_url()}/{run_id_str}/running_status")
    assert resp.status_code == code
    if code == 200:
        data = resp.json()
        assert data["id"] == run_id_str
        assert "status" in data
        assert "name" in data
        assert "currGen" in data
        assert "maxGen" in data
        assert "acceleratedRatio" in data
        assert "maxOffset" in data
        assert "createdAt" in data
        assert "updatedAt" in data


@pytest.mark.parametrize(
    "run_id_str, code, expected_total",
    [
        pytest.param(str(PENDING_UUID), 400, 0, id="pending"),
        pytest.param(str(RUNNING_UUID), 400, 0, id="running"),
        pytest.param(str(FAILURE_UUID), 400, 0, id="failure"),
        pytest.param(str(MISSING_UUID), 404, 0, id="missing"),
        pytest.param(str(SUCCESS_UUID), 200, 2, id="success_with_sols"),
    ],
)
async def test_get_result(
    pareto_solutions,
    client: AsyncClient,
    run_id_str: str,
    code: int,
    expected_total: int,
):
    resp = await client.get(f"{_url()}/{run_id_str}/result")
    assert resp.status_code == code
    if code == 200:
        data = resp.json()
        assert data["total"] == expected_total
        assert len(data["items"]) == expected_total


@pytest.mark.parametrize(
    "run_id_str, code",
    [
        pytest.param(str(PENDING_UUID), 204, id="pending"),
        pytest.param(str(RUNNING_UUID), 204, id="running"),
        pytest.param(str(FAILURE_UUID), 204, id="failure"),
        pytest.param(str(MISSING_UUID), 404, id="missing"),
        pytest.param(str(SUCCESS_UUID), 204, id="success"),
    ],
)
async def test_delete_optimize(runs, client: AsyncClient, run_id_str: str, code: int):
    resp = await client.delete(f"{_url()}/{run_id_str}")
    assert resp.status_code == code
    if code == 204:
        assert resp.content == b""
        # 删除后 GET 应 404
        get_resp = await client.get(f"{_url()}/{run_id_str}/running_status")
        assert get_resp.status_code == 404
        # 删除后列表查询不含该记录
        list_resp = await client.get(_url())
        assert list_resp.status_code == 200
        listed = {str(item["id"]) for item in list_resp.json()["items"]}
        assert run_id_str not in listed
    else:
        assert "detail" in resp.json()


@pytest.mark.parametrize(
    "run_id_str, code, broken",
    [
        pytest.param(str(PENDING_UUID), 200, True, id="pending"),
        pytest.param(str(RUNNING_UUID), 200, True, id="running"),
        pytest.param(str(SUCCESS_UUID), 400, False, id="success"),
        pytest.param(str(FAILURE_UUID), 400, False, id="failure"),
        pytest.param(str(MISSING_UUID), 404, False, id="missing"),
    ],
)
async def test_break_optimize(
    runs, client: AsyncClient, run_id_str: str, code: int, broken: bool
):
    """主动中断：PENDING/RUNNING → 200 且落库 FAILURE；终态/缺失 → 400/404。"""
    resp = await client.patch(f"{_url()}/{run_id_str}")
    assert resp.status_code == code

    if not broken:
        assert "detail" in resp.json()
        return

    # 200 契约：status 恒为 FAILURE，errorMsg 为"优化已被用户中断"
    data = resp.json()
    assert data["status"] == "FAILURE"
    assert data["errorMsg"] == "优化已被用户中断"

    # 终态恒定：running_status 不再变化
    status_resp = await client.get(f"{_url()}/{run_id_str}/running_status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "FAILURE"
    assert status_data["errorMsg"] == "优化已被用户中断"

    # 中断不产生结果
    result_resp = await client.get(f"{_url()}/{run_id_str}/result")
    assert result_resp.status_code == 400

    # 一次性操作：再次中断返回 400
    again = await client.patch(f"{_url()}/{run_id_str}")
    assert again.status_code == 400


# =============================================================================
# 任务/依赖快照
# =============================================================================


async def test_get_run_snapshot(runs, client: AsyncClient):
    """GET /optimize/{id}/tasks 返回运行创建时的任务与依赖快照。"""
    resp = await client.get(f"{_url()}/{SUCCESS_UUID}/tasks")
    assert resp.status_code == 200
    data = resp.json()
    tasks = data["tasks"]
    assert [t["id"] for t in tasks] == [1, 2]
    assert tasks[0]["code"] == "T-1"
    assert tasks[0]["name"] == "任务1"
    assert tasks[0]["duration"] == 2.0
    deps = data["dependencies"]
    assert len(deps) == 1
    assert deps[0]["taskId"] == 2
    assert deps[0]["predecessorId"] == 1
    assert deps[0]["type"] == "FS"


async def test_get_run_snapshot_missing(runs, client: AsyncClient):
    """不存在的运行返回 404。"""
    resp = await client.get(f"{_url()}/{MISSING_UUID}/tasks")
    assert resp.status_code == 404


async def test_get_run_snapshot_cross_project(
    runs, db_session: AsyncSession, client: AsyncClient
):
    """其他项目的运行返回 404（项目隔离）。"""
    db_session.add(Project(id=OTHER_PID, name="other", description="o", is_active=True))
    await db_session.commit()
    resp = await client.get(f"/projects/{OTHER_PID}/optimize/{SUCCESS_UUID}/tasks")
    assert resp.status_code == 404


async def test_get_run_snapshot_not_success(runs, client: AsyncClient):
    """PENDING 运行也有快照（快照创建时即写入，无需 SUCCESS）。"""
    resp = await client.get(f"{_url()}/{PENDING_UUID}/tasks")
    assert resp.status_code == 200


# =============================================================================
# 运行改名（PUT /optimize/{id}）
# =============================================================================


@pytest.mark.parametrize(
    "run_id_str, payload, expected_name",
    [
        pytest.param(str(SUCCESS_UUID), {"name": "重命名后"}, "重命名后", id="rename"),
        pytest.param(
            str(PENDING_UUID), {"name": "运行中改名"}, "运行中改名", id="rename_pending"
        ),
        pytest.param(str(RUNNING_UUID), {"name": None}, None, id="clear_name"),
    ],
)
async def test_rename_run(
    runs, client: AsyncClient, run_id_str: str, payload: dict, expected_name
):
    resp = await client.put(f"{_url()}/{run_id_str}", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == expected_name


async def test_rename_run_missing(runs, client: AsyncClient):
    """不存在的运行返回 404。"""
    resp = await client.put(f"{_url()}/{MISSING_UUID}", json={"name": "x"})
    assert resp.status_code == 404


async def test_rename_run_name_too_long(runs, client: AsyncClient):
    """标签超长返回 422。"""
    resp = await client.put(f"{_url()}/{SUCCESS_UUID}", json={"name": "x" * 101})
    assert resp.status_code == 422


# =============================================================================
# POST /optimize 快照持久化
# =============================================================================


@pytest_asyncio.fixture
async def snapshot_tasks(db_session: AsyncSession):
    """插入 2 个任务及 1 条依赖（用于 POST /optimize 快照持久化）"""
    tasks = [
        Task(id=10, project_id=PID, code="SNAP-1", name="snap1", duration=2.0),
        Task(id=11, project_id=PID, code="SNAP-2", name="snap2", duration=3.0),
    ]
    db_session.add_all(tasks)
    await db_session.commit()
    db_session.add(
        TaskDependency(
            project_id=PID,
            task_id=11,
            predecessor_id=10,
            type=DependencyType.FS,
        )
    )
    await db_session.commit()
    return tasks


async def test_create_optimize_persists_snapshot(
    monkeypatch, snapshot_tasks, db_session: AsyncSession, client: AsyncClient
):
    """POST /optimize 应持久化 name 与任务/依赖快照。"""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("src.routers.optimize._background_worker", _noop)

    resp = await client.post(f"{_url()}", json={"name": "串行 #1"})
    assert resp.status_code == 202
    run_id = uuid.UUID(resp.json()["runId"])

    run = await db_session.get(OptimizationRun, run_id)
    assert run is not None
    assert run.name == "串行 #1"
    assert [(t.id, t.code, t.name, t.duration) for t in run.task_snapshot] == [
        (10, "SNAP-1", "snap1", 2.0),
        (11, "SNAP-2", "snap2", 3.0),
    ]
    assert len(run.dependency_snapshot) == 1
    dep = run.dependency_snapshot[0]
    assert dep.task_id == 11
    assert dep.predecessor_id == 10
    assert dep.type == DependencyType.FS


async def test_create_optimize_without_name(
    monkeypatch, snapshot_tasks, db_session: AsyncSession, client: AsyncClient
):
    """未传 name 时运行标签为 None。"""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("src.routers.optimize._background_worker", _noop)

    resp = await client.post(f"{_url()}", json={})
    assert resp.status_code == 202
    run_id = uuid.UUID(resp.json()["runId"])
    run = await db_session.get(OptimizationRun, run_id)
    assert run is not None
    assert run.name is None


# =============================================================================
# 合并 Pareto 解集
# =============================================================================

MERGE_A_UUID = uuid.UUID("00000000-0000-0000-0000-00000000000a")
MERGE_B_UUID = uuid.UUID("00000000-0000-0000-0000-00000000000b")


def _strategy(task_id: int, mode: int, start: int) -> TaskStrategy:
    return TaskStrategy(task_id=task_id, mode=mode, start=start)


@pytest_asyncio.fixture
async def merge_runs(db_session: AsyncSession):
    """两个已完成的运行，各含 2 个带任务策略的 Pareto 解。"""
    snap_tasks, snap_deps = _snapshots()
    runs = [
        OptimizationRun(
            id=MERGE_A_UUID,
            project_id=PID,
            name="串行 #1",
            task_snapshot=snap_tasks,
            dependency_snapshot=snap_deps,
            pop_size=50,
            max_gen=100,
            irr=0.05,
            accelerated_ratio=0.8,
            max_offset=60,
            curr_gen=100,
            status=RunStatusEnum.SUCCESS,
        ),
        OptimizationRun(
            id=MERGE_B_UUID,
            project_id=PID,
            name="并行 #2",
            task_snapshot=snap_tasks,
            dependency_snapshot=snap_deps,
            pop_size=50,
            max_gen=100,
            irr=0.05,
            accelerated_ratio=0.8,
            max_offset=60,
            curr_gen=100,
            status=RunStatusEnum.SUCCESS,
        ),
    ]
    db_session.add_all(runs)
    await db_session.commit()

    solutions = [
        # run A 的解
        ParetoSolution(
            run_id=MERGE_A_UUID,
            strategies=[_strategy(1, 0, 0), _strategy(2, 0, 5)],
            cost=100.0,
            emission=50.0,
            duration=10.0,
            violations=[],
        ),
        ParetoSolution(
            run_id=MERGE_A_UUID,
            strategies=[_strategy(1, 1, 0), _strategy(2, 1, 4)],
            cost=200.0,
            emission=30.0,
            duration=15.0,
            violations=[],
        ),
        # run B 的解：第一个支配 run A 的第一个解（cost 相同但 duration 更短）
        ParetoSolution(
            run_id=MERGE_B_UUID,
            strategies=[_strategy(1, 0, 0), _strategy(2, 0, 4)],
            cost=100.0,
            emission=50.0,
            duration=8.0,
            violations=[],
        ),
        # 与 run A 第一个解目标值完全相同（重复解，应被去重）
        ParetoSolution(
            run_id=MERGE_B_UUID,
            strategies=[_strategy(1, 0, 0), _strategy(2, 0, 5)],
            cost=100.0,
            emission=50.0,
            duration=10.0,
            violations=[],
        ),
    ]
    db_session.add_all(solutions)
    await db_session.commit()
    return runs


async def test_merge_pareto_front(merge_runs, client: AsyncClient):
    """合并后应返回非支配前缘：剔除被支配与重复的解。"""
    resp = await client.post(
        f"{_url()}/merge",
        json={"run_ids": [str(MERGE_A_UUID), str(MERGE_B_UUID)]},
    )
    assert resp.status_code == 200
    data = resp.json()
    # 4 个输入：剔除被支配（A1）与重复（B2）后剩 2 个非支配解。
    # 前缘：(200,30,15) 碳排放最低 与 (100,50,8) 工期最短，互不支配。
    assert data["total"] == 2
    assert len(data["items"]) == 2
    obj = {(s["cost"], s["emission"], s["duration"]) for s in data["items"]}
    assert obj == {(100.0, 50.0, 8.0), (200.0, 30.0, 15.0)}
    # 来源 run_id 保留可追溯
    run_ids = {s["runId"] for s in data["items"]}
    assert run_ids == {str(MERGE_A_UUID), str(MERGE_B_UUID)}


async def test_merge_task_consistency_inconsistent(
    db_session: AsyncSession, merge_runs, client: AsyncClient
):
    """任务 id 集合不一致时返回 422 且错误消息明确（基于持久化快照校验）。"""
    bad_uuid = uuid.UUID("00000000-0000-0000-0000-00000000000c")
    snap_tasks, snap_deps = _snapshots(task_ids=(1, 2, 3))
    db_session.add(
        OptimizationRun(
            id=bad_uuid,
            project_id=PID,
            name="跨任务集",
            task_snapshot=snap_tasks,
            dependency_snapshot=snap_deps,
            pop_size=50,
            max_gen=100,
            irr=0.05,
            accelerated_ratio=0.8,
            max_offset=60,
            curr_gen=100,
            status=RunStatusEnum.SUCCESS,
        )
    )
    # 该运行覆盖的任务集不同（多了 task_id=3）
    db_session.add(
        ParetoSolution(
            run_id=bad_uuid,
            strategies=[_strategy(1, 0, 0), _strategy(2, 0, 4), _strategy(3, 0, 6)],
            cost=90.0,
            emission=20.0,
            duration=7.0,
            violations=[],
        )
    )
    await db_session.commit()

    resp = await client.post(
        f"{_url()}/merge",
        json={"run_ids": [str(MERGE_A_UUID), str(bad_uuid)]},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "任务 id 集合不一致" in detail
    assert str(MERGE_A_UUID) in detail and str(bad_uuid) in detail


async def test_merge_not_success(client: AsyncClient, runs):
    """包含未完成运行返回 400。"""
    resp = await client.post(
        f"{_url()}/merge",
        json={"run_ids": [str(PENDING_UUID)]},
    )
    assert resp.status_code == 400
    assert "detail" in resp.json()


async def test_merge_missing_run(client: AsyncClient, runs):
    """包含不存在的运行返回 404。"""
    resp = await client.post(
        f"{_url()}/merge",
        json={"run_ids": [str(MISSING_UUID)]},
    )
    assert resp.status_code == 404
    assert "detail" in resp.json()


async def test_merge_empty_run_ids(client: AsyncClient):
    """空 run_ids 返回 422（Pydantic min_length）。"""
    resp = await client.post(f"{_url()}/merge", json={"run_ids": []})
    assert resp.status_code == 422


# =============================================================================
# 资源约束 CRUD
# =============================================================================


@pytest.mark.parametrize(
    "query, expected_total",
    [
        pytest.param("", 3, id="all"),
        pytest.param("resource_id={r1}", 1, id="filter_resource_1"),
        pytest.param("resource_id={r2}", 1, id="filter_resource_2"),
        pytest.param("resource_id={r999}", 0, id="filter_nonexistent"),
        pytest.param("page=1&per_page=2", 3, id="page1_per_page2"),
    ],
)
async def test_list_constraints(
    constraints,
    resources_for_optimize,
    client: AsyncClient,
    query: str,
    expected_total: int,
):
    rids = _resource_ids(resources_for_optimize)
    rids["r999"] = 99999
    query = query.format(**rids)
    resp = await client.get(f"{_url()}/constraints?{query}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == expected_total
    if "page" in query:
        from urllib.parse import parse_qs

        params = parse_qs(query.lstrip("?"))
        page = int(params["page"][0])
        per_page = int(params["per_page"][0])
        expected_items = min(per_page, max(0, expected_total - (page - 1) * per_page))
        assert len(data["items"]) == expected_items
    else:
        assert len(data["items"]) == expected_total


@pytest.mark.parametrize(
    "payload, code",
    [
        pytest.param(
            # resource_id 为创建资源约束的必填字段
            {"max_usage": 50.0},
            422,
            id="missing_resource_id",
        ),
        pytest.param(
            {"resource_id": "{r1}", "max_usage": -1.0},
            422,
            id="max_usage_negative",
        ),
        pytest.param(
            {"resource_id": 999, "max_usage": 50.0},
            404,
            id="resource_not_found",
        ),
        pytest.param(
            # r1 已有约束（fixture 中创建）
            {"resource_id": "{r1}", "max_usage": 50.0},
            409,
            id="duplicate_constraint",
        ),
        pytest.param(
            # r4 尚未被约束，可成功创建
            {"resource_id": "{r4}", "max_usage": 300.0},
            201,
            id="success",
        ),
    ],
)
async def test_create_constraint(
    constraints,
    resources_for_optimize,
    client: AsyncClient,
    payload: dict,
    code: int,
):
    rids = _resource_ids(resources_for_optimize)
    payload = {
        k: rids.get(v.strip("{}"), v) if isinstance(v, str) else v
        for k, v in payload.items()
    }
    resp = await client.post(f"{_url()}/constraints", json=payload)
    assert resp.status_code == code
    if resp.status_code == 201:
        data = resp.json()
        assert "id" in data
        assert data["resourceId"] == payload["resource_id"]
        assert data["maxUsage"] == payload["max_usage"]
        assert "createdAt" in data
        assert "updatedAt" in data


async def test_create_constraint_cross_project(
    db_session: AsyncSession, resources_for_optimize, client: AsyncClient
):
    """跨项目测试：resource 属于其他项目时返回 400"""
    # 在 OTHER_PID 创建项目和资源
    db_session.add(Project(id=OTHER_PID, name="other", description="o", is_active=True))
    await db_session.commit()
    db_session.add(
        Resource(
            id=20001,
            project_id=OTHER_PID,
            name="other-r",
            description="o",
            category=ResourceCategory.labor,
        )
    )
    await db_session.commit()

    resp = await client.post(
        f"{_url()}/constraints",
        json={"resource_id": 20001, "max_usage": 50.0},
    )
    assert resp.status_code == 400
    assert "detail" in resp.json()


@pytest.mark.parametrize(
    "c_id, payload, code",
    [
        pytest.param(
            9999, {"resource_id": "{r1}", "max_usage": 200.0}, 404, id="not_found"
        ),
        pytest.param(
            "resource_1",
            {"resource_id": "{r1}", "max_usage": 200.0},
            200,
            id="update_max_usage",
        ),
        pytest.param(
            "resource_1",
            {"resource_id": "{r1}", "max_usage": 200.0, "description": "new desc"},
            200,
            id="update_multiple",
        ),
        pytest.param(
            "resource_1",
            {"resource_id": "{r1}", "max_usage": -5.0},
            422,
            id="invalid_max_usage",
        ),
    ],
)
async def test_update_constraint(
    constraints,
    resources_for_optimize,
    client: AsyncClient,
    c_id,
    payload: dict,
    code: int,
):
    rids = _resource_ids(resources_for_optimize)
    payload = {
        k: rids.get(v.strip("{}"), v) if isinstance(v, str) else v
        for k, v in payload.items()
    }
    real_id = (
        _constraint_ids(constraints).get(c_id, c_id) if isinstance(c_id, str) else c_id
    )
    resp = await client.put(f"{_url()}/constraints/{real_id}", json=payload)
    assert resp.status_code == code


@pytest.mark.parametrize(
    "c_id, code",
    [
        pytest.param(9999, 404, id="not_found"),
        pytest.param("resource_3", 204, id="success"),
    ],
)
async def test_delete_constraint(constraints, client: AsyncClient, c_id, code: int):
    real_id = (
        _constraint_ids(constraints).get(c_id, c_id) if isinstance(c_id, str) else c_id
    )
    resp = await client.delete(f"{_url()}/constraints/{real_id}")
    assert resp.status_code == code
    if code == 204:
        assert resp.content == b""


# =============================================================================
# 跨项目隔离
# =============================================================================


async def test_optimize_project_404(client: AsyncClient):
    """不存在的 project_id 应返回 404（依赖 _get_current_project）"""
    resp = await client.get(_url(pid=9999))
    assert resp.status_code == 404
    resp = await client.get(f"{_url(pid=9999)}/{PENDING_UUID}/running_status")
    assert resp.status_code == 404
    resp = await client.get(f"{_url(pid=9999)}/{PENDING_UUID}/result")
    assert resp.status_code == 404
    resp = await client.get(f"{_url(pid=9999)}/constraints")
    assert resp.status_code == 404
