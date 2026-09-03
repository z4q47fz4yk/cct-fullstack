"""碳排放补丁测试 - 临时用房 + 材料周转"""
# pyright: reportCallIssue=false

import asyncio
import math
import threading
from datetime import date

import numpy as np
import pytest
import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project
from src.models.resource import Resource, ResourceCategory
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.task import Task, TaskDependency
from src.schemas.optimize import RunConfig
from src.schemas.task import DependencyType
from src.services.optimization_adapter import (
    OptimizationAdapter,
    load_optimization_data,
)
from src.utils.nsga2_optimizer import (
    OptimizationRequest,
    OptimizationResult,
    ProgressCallback,
)

# 使用独立项目 ID 避免与现有测试数据冲突
PID = 9001


@pytest_asyncio.fixture
async def project_with_housing(db_session: AsyncSession):
    """创建独立测试项目"""
    project = Project(
        id=PID,
        name="test-carbon-project",
        description="test",
        is_active=True,
        housing_safety_factor=1.5,
        persons_per_room=6,
    )
    db_session.add(project)
    await db_session.commit()
    return project


@pytest_asyncio.fixture
async def resources(db_session: AsyncSession, project_with_housing):
    """创建测试资源"""
    objs = [
        Resource(
            id=9001,
            project_id=PID,
            name="人员生活",
            description="生活碳排放",
            category=ResourceCategory.labor,
            carbon_factor=2.5,
        ),
        Resource(
            id=9002,
            project_id=PID,
            name="模板",
            description="材料",
            category=ResourceCategory.material,
            unit_price=100.0,
            carbon_factor=50.0,
        ),
        Resource(
            id=9003,
            project_id=PID,
            name="集装箱",
            description="临时用房",
            category=ResourceCategory.material,
            carbon_factor=200.0,
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


@pytest_asyncio.fixture
async def tasks(db_session: AsyncSession):
    """创建测试任务"""
    objs = [
        Task(id=9001, project_id=PID, code="CT1", name="任务1", duration=10.0),
        Task(id=9002, project_id=PID, code="CT2", name="任务2", duration=8.0),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


@pytest_asyncio.fixture
async def reuse_config(db_session: AsyncSession, resources):
    """创建资源周转配置"""
    config = ResourceReuseConfig(
        project_id=PID,
        resource_id=9002,  # 模板
        max_reuses=5,
        reuse_count=3,
        affect_cost=True,
        description="模板周转配置",
    )
    db_session.add(config)
    await db_session.commit()
    return config


@pytest_asyncio.fixture
async def labor_usages(db_session: AsyncSession, tasks, resources):
    """创建 labor 资源用量（用于 peak_personnel 测试）"""
    objs = [
        TaskResourceUsage(
            project_id=PID,
            task_id=9001,
            resource_id=9001,  # 人员生活
            usage_date=date(2026, 1, 1),
            quantity=100.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=PID,
            task_id=9002,
            resource_id=9001,  # 人员生活
            usage_date=date(2026, 1, 1),
            quantity=80.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=PID,
            task_id=9001,
            resource_id=9001,  # 人员生活
            usage_date=date(2026, 1, 1),
            quantity=120.0,
            usage_type=UsageType.PLANNED,
        ),
        TaskResourceUsage(
            project_id=PID,
            task_id=9002,
            resource_id=9001,  # 人员生活
            usage_date=date(2026, 1, 1),
            quantity=90.0,
            usage_type=UsageType.PLANNED,
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


def _url(pid: int = PID) -> str:
    return f"/projects/{pid}/optimize"


# ===========================================================================
# Reuse Config CRUD
# ===========================================================================


async def test_create_reuse_config(resources, client: AsyncClient):
    """创建资源周转配置"""
    resp = await client.post(
        f"{_url()}/reuse-configs",
        json={
            "resourceId": 9002,
            "maxReuses": 5,
            "reuseCount": 3,
            "affectCost": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["resourceId"] == 9002
    assert data["maxReuses"] == 5
    assert data["reuseCount"] == 3
    assert data["affectCost"] is True


async def test_create_reuse_config_duplicate(reuse_config, client: AsyncClient):
    """重复创建返回 409"""
    resp = await client.post(
        f"{_url()}/reuse-configs",
        json={"resourceId": 9002, "maxReuses": 2, "reuseCount": 1},
    )
    assert resp.status_code == 409


async def test_create_reuse_config_resource_not_found(resources, client: AsyncClient):
    """资源不存在返回 404"""
    resp = await client.post(
        f"{_url()}/reuse-configs",
        json={"resourceId": 99999, "maxReuses": 2, "reuseCount": 1},
    )
    assert resp.status_code == 404


async def test_list_reuse_configs(reuse_config, client: AsyncClient):
    """列出资源周转配置"""
    resp = await client.get(f"{_url()}/reuse-configs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


async def test_update_reuse_config(reuse_config, client: AsyncClient):
    """更新资源周转配置"""
    resp = await client.get(f"{_url()}/reuse-configs")
    config_id = resp.json()["items"][0]["id"]

    resp = await client.put(
        f"{_url()}/reuse-configs/{config_id}",
        json={"max_reuses": 10, "reuse_count": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["maxReuses"] == 10
    assert data["reuseCount"] == 2


async def test_delete_reuse_config(reuse_config, client: AsyncClient):
    """删除资源周转配置"""
    resp = await client.get(f"{_url()}/reuse-configs")
    config_id = resp.json()["items"][0]["id"]

    resp = await client.delete(f"{_url()}/reuse-configs/{config_id}")
    assert resp.status_code == 204

    resp = await client.get(f"{_url()}/reuse-configs")
    assert resp.json()["total"] == 0


async def test_delete_reuse_config_not_found(client: AsyncClient):
    """删除不存在的配置返回 404"""
    resp = await client.delete(f"{_url()}/reuse-configs/99999")
    assert resp.status_code == 404


# ===========================================================================
# Project Housing 字段
# ===========================================================================


async def test_project_housing_fields(project_with_housing, client: AsyncClient):
    """Project housing 字段正确返回（snake_case）"""
    resp = await client.get(f"/project/{PID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["housing_safety_factor"] == 1.5
    assert data["persons_per_room"] == 6


async def test_project_update_housing_fields(project_with_housing, client: AsyncClient):
    """更新 Project housing 字段"""
    resp = await client.put(
        f"/project/{PID}",
        json={
            "housing_safety_factor": 2.0,
            "persons_per_room": 8,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["housing_safety_factor"] == 2.0
    assert data["persons_per_room"] == 8


# ===========================================================================
# RunConfig usage_type
# ===========================================================================


async def test_run_config_usage_type_default():
    """RunConfig 默认 usage_type 为 PLANNED（计划阶段做优化）"""
    config = RunConfig()
    assert config.usage_type == "PLANNED"


async def test_run_config_usage_type_planned():
    """RunConfig 可以设置 usage_type 为 PLANNED"""
    config = RunConfig(usage_type="PLANNED")
    assert config.usage_type == "PLANNED"


# ===========================================================================
# Adapter 核心逻辑
# ===========================================================================


async def test_adapter_reuse_pre_correction(
    db_session: AsyncSession,
    project_with_housing,
    resources,
    reuse_config,
):
    """Adapter 预修正周转资源的 unit_price 和 carbon_factor"""
    data = await load_optimization_data(db_session, PID)
    adapter = OptimizationAdapter(
        data,
        RunConfig(pop_size=10, max_gen=1),
    )
    request = adapter.to_nsga2_request("test-session")

    # 模板（resource_id=9002）有周转配置：max_reuses=5, reuse_count=3, affect_cost=True
    # divisor = 5 * 3 = 15
    # effective_unit_price = 100 / 15 = 6.666...
    # effective_carbon_factor = 50 / 15 = 3.333...
    template_info = request.resource_costs[9002]
    assert abs(template_info.unit_price - 100.0 / 15) < 0.01
    assert abs(template_info.carbon_factor - 50.0 / 15) < 0.01


async def test_adapter_labor_by_task_mode(
    db_session: AsyncSession,
    project_with_housing,
    resources,
    tasks,
    labor_usages,
):
    """Adapter 根据 usage_type 选择不同的 labor 聚合字典"""
    # ACTUAL: task9001=100, task9002=80
    data_actual = await load_optimization_data(db_session, PID, UsageType.ACTUAL)
    assert data_actual.actual_labor_by_task[9001] == 100.0
    assert data_actual.actual_labor_by_task[9002] == 80.0

    # PLANNED: task9001=120, task9002=90
    data_planned = await load_optimization_data(db_session, PID, UsageType.PLANNED)
    assert data_planned.planned_labor_by_task[9001] == 120.0
    assert data_planned.planned_labor_by_task[9002] == 90.0


async def test_adapter_preserves_dependency_type(
    db_session: AsyncSession,
    project_with_housing,
    resources,
    tasks,
):
    """Adapter 应将 SS 类型传入 NSGA-II 请求。"""
    db_session.add(
        TaskDependency(
            task_id=9002,
            predecessor_id=9001,
            project_id=PID,
            type=DependencyType.SS,
        )
    )
    await db_session.commit()

    data = await load_optimization_data(db_session, PID)
    request = OptimizationAdapter(
        data,
        RunConfig(pop_size=10, max_gen=1),
    ).to_nsga2_request("test-session")

    assert len(request.dependencies) == 1
    assert request.dependencies[0].type == "SS"


async def test_adapter_housing_config(
    db_session: AsyncSession,
    project_with_housing,
    resources,
):
    """Adapter 注入 housing 配置"""
    project_with_housing.housing_resource_id = 9003
    db_session.add(project_with_housing)
    await db_session.commit()

    data = await load_optimization_data(db_session, PID)
    adapter = OptimizationAdapter(data, RunConfig(pop_size=10, max_gen=1))
    request = adapter.to_nsga2_request("test-session")

    assert request.housing_resource_carbon_factor == 200.0
    assert request.housing_safety_factor == 1.5
    assert request.persons_per_room == 6
    assert request.housing_enabled is True


async def test_adapter_housing_not_configured(
    db_session: AsyncSession,
    project_with_housing,
    resources,
):
    """未配置 housing_resource_id 时 carbon_factor 为 0"""
    data = await load_optimization_data(db_session, PID)
    adapter = OptimizationAdapter(data, RunConfig(pop_size=10, max_gen=1))
    request = adapter.to_nsga2_request("test-session")

    assert request.housing_resource_carbon_factor == 0.0
    assert request.housing_enabled is False


async def test_adapter_housing_enabled_with_zero_carbon_factor(
    db_session: AsyncSession,
    project_with_housing,
    resources,
):
    """已配置临时用房但资源碳因子为 0：housing_enabled 仍为 True。

    回归：修复前 carbon_factor=0 被当作"未启用"，房间数恒为 0
    （线上数据 集装箱 carbon_factor=0 → peak=26 但 housing_rooms=0）。
    """
    project_with_housing.housing_resource_id = 9003
    db_session.add(project_with_housing)
    await db_session.commit()
    # 碳因子清为 0（模拟线上集装箱资源）
    housing = next(r for r in resources if r.id == 9003)
    housing.carbon_factor = 0.0
    db_session.add(housing)
    await db_session.commit()

    data = await load_optimization_data(db_session, PID)
    request = OptimizationAdapter(
        data, RunConfig(pop_size=10, max_gen=1)
    ).to_nsga2_request("test-session")

    assert request.housing_resource_carbon_factor == 0.0
    assert request.housing_enabled is True


# ===========================================================================
# Peak Personnel 计算
# ===========================================================================


def test_compute_peak_personnel_basic():
    """基础 peak_personnel 计算"""
    from src.utils.nsga2_optimizer import ConstructionProblem

    problem = ConstructionProblem(
        n_tasks=2,
        task_ids=[1, 2],
        base_costs_matrix=np.zeros((2, 5)),
        base_emissions_matrix=np.zeros((2, 5)),
        task_id_to_duration={1: 10.0, 2: 8.0},
        base_resource_usage_matrix=np.zeros((2, 0)),
        resource_constraints=np.array([]),
        in_degree={1: 0, 2: 0},
        graph={1: [], 2: []},
        task_id_to_idx={1: 0, 2: 1},
        labor_by_task_idx=np.array([100.0, 80.0]),
    )

    # T1: 100 工日 / 10 天 = 10 人/天，运行 0-10
    # T2: 80 工日 / 8 天 = 10 人/天，运行 0-8
    # peak = 10 + 10 = 20（并行时）
    T_G = np.array([10.0, 8.0])
    earliest_starts = np.array([0.0, 0.0])
    peak = problem._compute_peak_personnel(T_G, earliest_starts)
    assert peak == 20


def test_compute_peak_personnel_no_labor():
    """无 labor 数据时返回 0"""
    from src.utils.nsga2_optimizer import ConstructionProblem

    problem = ConstructionProblem(
        n_tasks=1,
        task_ids=[1],
        base_costs_matrix=np.zeros((1, 5)),
        base_emissions_matrix=np.zeros((1, 5)),
        task_id_to_duration={1: 10.0},
        base_resource_usage_matrix=np.zeros((1, 0)),
        resource_constraints=np.array([]),
        in_degree={1: 0},
        graph={1: []},
        task_id_to_idx={1: 0},
        labor_by_task_idx=np.array([0.0]),
    )

    T_G = np.array([10.0])
    earliest_starts = np.array([0.0])
    peak = problem._compute_peak_personnel(T_G, earliest_starts)
    assert peak == 0


# ============================================================================
# 回归测试：Bug 1（int 截断）+ Bug 2（Pareto 去重）
# 参考 plan：/Users/pengyongtang/.claude/plans/nsga2-bug-shiny-stearns.md
# ============================================================================


def test_calculate_resource_violations_counts_subday_duration():
    """加速任务（T_G < 1 天）的 daily_rate 必须被计入 violation 矩阵。

    修复前：int(0.8) == 0，任务被完全跳过。
    修复后：math.ceil(0.8) == 1，任务占用第 0 天。
    """
    from src.utils.nsga2_optimizer import calculate_resource_violations_vectorized

    # 1 个任务，dur=0.8，资源量为 80（一天的速率 = 80 / 1 = 80）
    # 资源约束 = 50：违反量 = max(0, 80 - 50) = 30
    durations = np.array([0.8])
    earliest_starts = np.array([0.0])
    resource_usage = np.array([[80.0]])  # 1 task × 1 resource
    resource_constraints = np.array([50.0])

    violations = calculate_resource_violations_vectorized(
        durations, earliest_starts, resource_usage, resource_constraints
    )
    # 修复前违反量 = 0（任务被跳过），修复后违反量 = 30
    assert violations.shape == (1,)
    assert violations[0] == pytest.approx(30.0)


def test_compute_peak_personnel_counts_subday_duration():
    """加速任务的用工不能因 int() 截断而被忽略。"""
    from src.utils.nsga2_optimizer import ConstructionProblem

    problem = ConstructionProblem(
        n_tasks=1,
        task_ids=[1],
        base_costs_matrix=np.zeros((1, 5)),
        base_emissions_matrix=np.zeros((1, 5)),
        task_id_to_duration={1: 1.0},
        base_resource_usage_matrix=np.zeros((1, 0)),
        resource_constraints=np.array([]),
        in_degree={1: 0},
        graph={1: []},
        task_id_to_idx={1: 0},
        labor_by_task_idx=np.array([10.0]),
    )
    # 加速后 T_G = 0.8；10 工日 / 0.8 = 12.5 人/天
    T_G = np.array([0.8])
    earliest_starts = np.array([0.0])
    peak = problem._compute_peak_personnel(T_G, earliest_starts)
    # 修复前：int(0.8) == 0 ⇒ if end > start 跳过 ⇒ peak = 0
    # 修复后：math.ceil(0.8) == 1 ⇒ daily[0:1] += 12.5 ⇒ peak = int(12.5) = 12
    assert peak > 0
    assert peak == 12


def test_compute_housing_rooms_with_zero_carbon_factor():
    """已配置临时用房、碳因子为 0 时房间数仍按峰值人数派生。

    回归：修复前房间数被 carbon_factor>0 开关门控，碳因子为 0 时恒为 0
    （线上数据 peak=26、safety=1.2、persons=4 → 应返回 ceil(26*1.2/4)=8）。
    """
    from src.utils.nsga2_optimizer import ConstructionProblem

    problem = ConstructionProblem(
        n_tasks=1,
        task_ids=[1],
        base_costs_matrix=np.zeros((1, 5)),
        base_emissions_matrix=np.zeros((1, 5)),
        task_id_to_duration={1: 10.0},
        base_resource_usage_matrix=np.zeros((1, 0)),
        resource_constraints=np.array([]),
        in_degree={1: 0},
        graph={1: []},
        task_id_to_idx={1: 0},
        labor_by_task_idx=np.array([100.0]),
        housing_enabled=True,
        housing_resource_carbon_factor=0.0,
        housing_safety_factor=1.2,
        persons_per_room=4,
    )
    assert problem._compute_housing_rooms(26) == 8  # ceil(26*1.2/4)
    assert problem._compute_housing_rooms(0) == 0


def test_compute_housing_rooms_disabled_when_not_configured():
    """未配置临时用房（housing_enabled=False）时房间数恒为 0。"""
    from src.utils.nsga2_optimizer import ConstructionProblem

    problem = ConstructionProblem(
        n_tasks=1,
        task_ids=[1],
        base_costs_matrix=np.zeros((1, 5)),
        base_emissions_matrix=np.zeros((1, 5)),
        task_id_to_duration={1: 10.0},
        base_resource_usage_matrix=np.zeros((1, 0)),
        resource_constraints=np.array([]),
        in_degree={1: 0},
        graph={1: []},
        task_id_to_idx={1: 0},
        labor_by_task_idx=np.array([100.0]),
        housing_enabled=False,
        housing_resource_carbon_factor=200.0,
        housing_safety_factor=1.2,
        persons_per_room=4,
    )
    assert problem._compute_housing_rooms(26) == 0


def _housing_request(session_id: str, housing_enabled: bool) -> OptimizationRequest:
    """最小优化请求：1 个任务 + labor 用量 + 临时用房配置。

    labor=100 工日 / 工期 10 天 → peak=10 人。
    """
    from src.utils.nsga2_optimizer import NSGA2Config, TaskInput

    return OptimizationRequest(
        session_id=session_id,
        tasks=[TaskInput(id=1, code="T-1", duration=10.0)],
        dependencies=[],
        resource_usages=[],
        resource_costs={},
        resource_constraints={},
        personnel_living_carbon_factor=0.0,
        accelerated_ratio=0.8,
        max_offset=10,
        nsga2_config=NSGA2Config(pop_size=8, n_generations=3, seed=1),
        labor_by_task_idx=np.array([100.0]),
        housing_enabled=housing_enabled,
        housing_resource_carbon_factor=0.0,
        housing_safety_factor=1.2,
        persons_per_room=4,
    )


def test_run_optimization_housing_rooms_derived_from_peak():
    """端到端：碳因子为 0 但已配置临时用房时，解的 housing_rooms 由峰值派生。

    修复前：carbon_factor=0 → housing_rooms 恒为 0。
    修复后：每个解 housing_rooms == ceil(peak*1.2/4)，且存在 >0 的解。
    """
    from src.utils.nsga2_optimizer import run_optimization

    cb = _CollectingCallback()
    run_optimization(_housing_request("housing-e2e", housing_enabled=True), cb)
    assert cb.result is not None
    assert cb.result.status == "completed"
    assert len(cb.result.solutions) >= 1
    # 每个解的房间数与峰值人数一致（不受碳因子=0 影响）
    for sol in cb.result.solutions:
        assert sol.housing_rooms == math.ceil(sol.peak_personnel * 1.2 / 4)
    # labor 数据存在，至少一个解 peak>0 ⇒ 房间数>0
    assert any(sol.housing_rooms > 0 for sol in cb.result.solutions)


def test_run_optimization_housing_rooms_zero_when_not_configured():
    """端到端：未配置临时用房时房间数恒为 0（行为不回退）。"""
    from src.utils.nsga2_optimizer import run_optimization

    cb = _CollectingCallback()
    run_optimization(
        _housing_request("housing-not-configured", housing_enabled=False), cb
    )
    assert cb.result is not None
    assert cb.result.status == "completed"
    assert all(sol.housing_rooms == 0 for sol in cb.result.solutions)
    """子天工期（es=0.3, ee=0.7）走正常折现路径，不再被截断为 D=0。

    修复前：int(0.3)=0, int(0.7)=0, D=0, calculate_present_value 返回 C（不折现）。
    修复后：math.ceil(0.3)=1, math.ceil(0.7)=1, D=1, 落入正常折现逻辑。
    """
    from src.utils.nsga2_optimizer import calculate_present_value

    C = 1000.0
    # 注意：调用方传入的是 math.ceil(es) / math.ceil(ee)，
    # 因此这里直接传 1, 1 验证 "D=1 时正常折现"
    pv = calculate_present_value(1, 2, C, r=0.05 / 12)
    # D=1 跨越 1 个结算月首段，cost_ratio ≈ 1 / (2/3*30) ... 由代码决定；
    # 我们只断言：(a) D=1 不再短路返回 C，(b) pv < C 且 pv > 0
    assert 0 < pv < C


def test_dedup_pareto_indices_keeps_unique_objectives():
    """_dedup_pareto_indices：目标空间重复时只保留第一行。"""
    from src.utils.nsga2_optimizer import _dedup_pareto_indices

    F = np.array([
        [100.0, 200.0, 10.0],
        [100.0, 200.0, 10.0],  # 完全重复
        [100.0, 200.0, 10.0],  # 完全重复
        [150.0, 180.0, 12.0],
    ])
    X = np.array([
        [0, 1, 5],
        [1, 1, 7],
        [2, 1, 9],
        [0, 1, 3],
    ])
    idx = _dedup_pareto_indices(F, X)
    # 期望保留第 0 行（首次出现的 F）和第 3 行（不同 F）
    assert idx == [0, 3]


def test_dedup_pareto_indices_handles_floating_point_noise():
    """相同目标应被去重，即使因浮点误差存在微小差异。"""
    from src.utils.nsga2_optimizer import _dedup_pareto_indices

    F = np.array([
        [100.0, 200.0, 10.0],
        [100.0 + 1e-9, 200.0 - 1e-9, 10.0 + 1e-9],  # 浮点噪声但同一解
        [150.0, 180.0, 12.0],
    ])
    X = np.array([
        [0, 1, 5],
        [1, 2, 6],
        [2, 3, 7],
    ])
    idx = _dedup_pareto_indices(F, X)
    # round 到 6 位小数后第 0/1 行 F 一致；保留首次出现的第 0 行
    assert idx == [0, 2]


def test_dedup_pareto_indices_within_same_F_keeps_distinct_X():
    """同 F、不同 X（罕见但可能）：保留首次出现的 X 行。"""
    from src.utils.nsga2_optimizer import _dedup_pareto_indices

    F = np.array([
        [100.0, 200.0, 10.0],
        [100.0, 200.0, 10.0],  # 同 F
    ])
    X = np.array([
        [0, 1, 5],
        [1, 2, 6],  # 不同 X
    ])
    idx = _dedup_pareto_indices(F, X)
    # F 第一次出现都去重到第 0 行；去重后 X 也只有 1 行
    assert idx == [0]


def test_dedup_pareto_indices_preserves_pymoo_order():
    """pymoo 通常不保证 F 按数值排序返回；去重后必须保持 pymoo 原序（np.sort）。"""
    from src.utils.nsga2_optimizer import _dedup_pareto_indices

    # F 顺序就是 pymoo 输出顺序，我们去重后必须保持这个顺序
    F = np.array([
        [200.0, 100.0, 5.0],  # 第 0 行（pymoo 顺序中最先）
        [100.0, 200.0, 10.0],  # 第 1 行
        [200.0, 100.0, 5.0],  # 与第 0 行 F 重复
    ])
    X = np.array([[0, 0], [1, 1], [2, 2]])
    idx = _dedup_pareto_indices(F, X)
    assert idx == [0, 1]


async def test_optimization_consumer_uses_ceil_for_strategy_start():
    """QueueBackedCallback.on_complete 必须将 sol.starts[idx] 向上取整为天数。

    直接调用回调逻辑校验，而非启动完整 NSGA2：
    构造 Result.solutions[0].starts 含小数，断言产生的 TaskStrategy.start
    不等于 int 截断值（即不会变 0），等于 math.ceil 值。
    （async def：回调构造需运行中的事件循环以捕获 loop）
    """
    from src.services.optimization_consumer import QueueBackedCallback
    from src.utils.nsga2_optimizer import OptimizationResult, SolutionOutput

    cb = QueueBackedCallback(
        session_id="s1",
        queue=None,
        task_ids=[10, 20],
        constraint_map={},
    )

    # 1 个解：modes = [ACCELERATED, NORMAL]，starts = [0.0, 0.8]
    sol = SolutionOutput(
        solution_id=0,
        modes=[1, 0],  # TaskMode 1 = ACCELERATED
        offsets=[0, 0],
        starts=[0.0, 0.8],
        cost=100.0,
        emission=50.0,
        duration=10.0,
        violations={},
        peak_personnel=0,
        housing_rooms=0,
    )

    result = OptimizationResult(session_id="s1", status="completed", solutions=[sol])

    # 调用 on_complete 但拦截 queue.put_nowait，只取 db_solutions
    captured = {}

    class _CaptureQueue:
        def put_nowait(self, event):
            captured["event"] = event

    cb._queue = _CaptureQueue()
    cb.on_complete(result)
    # on_complete 经 call_soon_threadsafe 入队，put 在事件循环中异步执行，
    # 让出一次控制权等待其完成
    await asyncio.sleep(0)

    db_sols = captured["event"].db_solutions
    assert db_sols is not None and len(db_sols) == 1
    strategies = db_sols[0].strategies
    assert len(strategies) == 2
    # 第 0 个任务 starts = 0.0，ceil(0) = 0；第 1 个任务 starts = 0.8，ceil = 1
    # 修复前：int(0.8) == 0 ⇒ 与第 0 个任务的 start 相同（撞到 0）
    # 修复后：ceil(0.8) == 1 ⇒ 与第 0 个任务的 start 不同（消除撞日）
    assert strategies[0].start == 0
    assert strategies[1].start == 1


# ===========================================================================
# 主动中断（PATCH /optimize/{id} 协作协议）
# ===========================================================================


class _CollectingCallback(ProgressCallback):
    """记录进度代与最终结果，用于验证 run_optimization 的中断行为。"""

    def __init__(self):
        self.generations: list[int] = []
        self.result: OptimizationResult | None = None

    def on_progress(
        self, session_id: str, current_generation: int, total_generations: int
    ) -> None:
        self.generations.append(current_generation)

    def on_complete(self, result: OptimizationResult) -> None:
        self.result = result


def _minimal_abort_request(session_id: str = "abort-test") -> OptimizationRequest:
    """最小优化请求：1 个任务、无依赖、无资源约束。"""
    from src.utils.nsga2_optimizer import NSGA2Config, TaskInput

    return OptimizationRequest(
        session_id=session_id,
        tasks=[TaskInput(id=1, code="T-1", duration=2.0)],
        dependencies=[],
        resource_usages=[],
        resource_costs={},
        resource_constraints={},
        personnel_living_carbon_factor=0.0,
        accelerated_ratio=0.8,
        max_offset=10,
        nsga2_config=NSGA2Config(pop_size=4, n_generations=5, seed=1),
    )


def test_run_optimization_aborts_when_flag_preset():
    """abort_event 预先置位：run_optimization 入口直接以中断结果退出。"""
    from src.utils.nsga2_optimizer import run_optimization

    cb = _CollectingCallback()
    abort_event = threading.Event()
    abort_event.set()

    run_optimization(_minimal_abort_request(), cb, abort_event)

    assert cb.generations == []  # 未启动任何进化
    assert cb.result is not None
    assert cb.result.status == "failed"
    assert cb.result.solutions == []
    assert cb.result.error_message == "优化已被用户中断"


class _AbortingCallback(_CollectingCallback):
    """on_progress 触发后立刻置位中断标记，模拟运行中途 break。"""

    def __init__(self, abort_event: threading.Event):
        super().__init__()
        self.abort_event = abort_event

    def on_progress(
        self, session_id: str, current_generation: int, total_generations: int
    ) -> None:
        super().on_progress(session_id, current_generation, total_generations)
        self.abort_event.set()


def test_run_optimization_aborts_mid_run():
    """运行中途置位：on_progress 中 set 后，下一代 notify 抛中断，提前终止。"""
    from src.utils.nsga2_optimizer import run_optimization

    abort_event = threading.Event()
    cb = _AbortingCallback(abort_event)

    run_optimization(_minimal_abort_request(), cb, abort_event)

    assert len(cb.generations) >= 1  # 确实已开始进化
    assert cb.result is not None
    assert cb.result.status == "failed"
    assert cb.result.solutions == []
    assert cb.result.error_message == "优化已被用户中断"


def test_abort_registry_lifecycle():
    """中断注册表：注册/置位/查询/移除的完整生命周期。"""
    from src.services.optimization_consumer import (
        is_abort_requested,
        register_abort_event,
        request_abort,
        unregister_abort_event,
    )

    sid = "registry-test"
    unregister_abort_event(sid)  # 清理可能的残留

    assert not is_abort_requested(sid)
    assert request_abort(sid) is False  # 未注册时 best-effort 返回 False

    event = register_abort_event(sid)
    assert not event.is_set()
    assert not is_abort_requested(sid)

    assert request_abort(sid) is True
    assert event.is_set()
    assert is_abort_requested(sid)

    unregister_abort_event(sid)
    assert not is_abort_requested(sid)
    assert request_abort(sid) is False
