from src.models.task import Task, TaskDependency
from src.schemas.task import DependencyType
from src.utils.critical_path_method import calculate_critical_path
from src.utils.nsga2_optimizer import (
    DependencyInput,
    OptimizationRequest,
    TaskInput,
    build_problem,
    compute_total_time,
)


def _task(task_id: int, duration: float) -> Task:
    return Task(
        id=task_id,
        project_id=1,
        code=f"T-{task_id}",
        name=f"任务{task_id}",
        duration=duration,
    )


def _dependency(
    task_id: int, predecessor_id: int, dependency_type: DependencyType
) -> TaskDependency:
    return TaskDependency(
        task_id=task_id,
        predecessor_id=predecessor_id,
        project_id=1,
        type=dependency_type,
    )


def test_critical_path_ss_uses_successor_latest_start():
    """SS 关系的反向传递应使用后继任务的 LS。"""
    tasks = [_task(1, 2.0), _task(2, 2.0), _task(3, 10.0)]
    dependencies = [_dependency(2, 1, DependencyType.SS)]

    result = calculate_critical_path(tasks, dependencies)

    assert result["critical_duration"] == 10.0
    assert result["critical_task_ids"] == {3}
    assert result["task_schedules"][1]["es"] == 0.0
    assert result["task_schedules"][2]["es"] == 0.0
    assert result["task_schedules"][1]["ls"] == 8.0
    assert result["task_schedules"][2]["ls"] == 8.0


def test_nsga2_compute_total_time_supports_ss():
    """NSGA-II 中 SS 关系不应把后继任务推迟到前置任务结束后。"""
    total_time, starts = compute_total_time(
        durations=[10.0, 3.0],
        start_offsets=[0, 0],
        in_degree={1: 0, 2: 1},
        graph={1: [(2, "SS")], 2: []},
        task_ids=[1, 2],
        task_id_to_idx={1: 0, 2: 1},
    )

    assert starts == {1: 0, 2: 0}
    assert total_time == 10.0


def test_nsga2_compute_total_time_keeps_fs_behavior():
    """FS 关系仍按前置任务完成后才能开始计算。"""
    total_time, starts = compute_total_time(
        durations=[10.0, 3.0],
        start_offsets=[0, 0],
        in_degree={1: 0, 2: 1},
        graph={1: [(2, "FS")], 2: []},
        task_ids=[1, 2],
        task_id_to_idx={1: 0, 2: 1},
    )

    assert starts == {1: 0, 2: 10.0}
    assert total_time == 13.0


def test_build_problem_preserves_dependency_type():
    """构建优化问题时应保留数据库中的依赖类型。"""
    request = OptimizationRequest(
        session_id="test-session",
        tasks=[
            TaskInput(id=1, code="T-1", duration=10.0),
            TaskInput(id=2, code="T-2", duration=3.0),
        ],
        dependencies=[DependencyInput(predecessor_id=1, task_id=2, type="SS")],
        resource_usages=[],
        resource_costs={},
        resource_constraints={},
        personnel_living_carbon_factor=0.0,
    )

    problem, _ = build_problem(request)

    assert problem.graph[1] == [(2, "SS")]
