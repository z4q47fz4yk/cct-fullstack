"""计划排程工具：CPM + 显式开始时间 + 依赖校验。"""

from collections import deque
from dataclasses import dataclass, field
from typing import Sequence

from src.models.task import Task, TaskDependency


@dataclass
class PlanScheduleResult:
    """计划排程结果。"""

    schedule: dict[int, tuple[float, float]] = field(default_factory=dict)
    critical_duration: float = 0.0
    violations: list[str] = field(default_factory=list)


def schedule_plan(
    tasks: Sequence[Task],
    dependencies: Sequence[TaskDependency],
    durations: dict[int, float],
    fixed_starts: dict[int, float] | None = None,
) -> PlanScheduleResult:
    """按依赖关系计算任务开始/结束时间。

    与 ``critical_path_method.calculate_critical_path`` 口径一致（支持
    FS/SS/FF）；额外支持显式开始时间：显式 start 早于依赖约束时
    记录冲突并取 max(约束, 显式)，由调用方决定是否报错。

    Args:
        tasks: 项目任务列表
        dependencies: 依赖关系列表
        durations: task_id -> 调整后工期
        fixed_starts: task_id -> 显式开始时间（天）

    Returns:
        PlanScheduleResult：schedule 为 {task_id: (start, end)}。
    """
    fixed_starts = fixed_starts or {}
    task_ids = {t.id for t in tasks if t.id is not None}
    if not task_ids:
        return PlanScheduleResult()

    duration_map: dict[int, float] = {
        cast_id(t.id): durations.get(cast_id(t.id), t.duration)
        for t in tasks
        if t.id is not None
    }
    task_codes: dict[int, str] = {
        cast_id(t.id): t.code for t in tasks if t.id is not None
    }

    predecessors: dict[int, list[tuple[int, str]]] = {t: [] for t in task_ids}
    successors: dict[int, list[tuple[int, str]]] = {t: [] for t in task_ids}
    for dep in dependencies:
        if dep.task_id in task_ids and dep.predecessor_id in task_ids:
            dep_type = dep.type.value if hasattr(dep.type, "value") else str(dep.type)
            predecessors[dep.task_id].append((dep.predecessor_id, dep_type))
            successors[dep.predecessor_id].append((dep.task_id, dep_type))

    # Kahn 拓扑排序
    in_degree = {t: len(predecessors[t]) for t in task_ids}
    queue: deque[int] = deque([t for t in task_ids if in_degree[t] == 0])
    topo_order: list[int] = []
    while queue:
        current = queue.popleft()
        topo_order.append(current)
        for succ, _ in successors[current]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)
    if len(topo_order) != len(task_ids):
        raise ValueError("依赖关系存在循环，无法计算施工计划")

    start: dict[int, float] = {}
    end: dict[int, float] = {}
    violations: list[str] = []
    for tid in topo_order:
        computed = 0.0
        duration = duration_map[tid]
        for pred, dep_type in predecessors[tid]:
            pred_start = start[pred]
            pred_end = end[pred]
            if dep_type == "SS":
                computed = max(computed, pred_start)
            elif dep_type == "FF":
                computed = max(computed, pred_end - duration)
            else:  # FS / 未知类型
                computed = max(computed, pred_end)

        fixed = fixed_starts.get(tid)
        if fixed is not None:
            if fixed + 1e-9 < computed:
                violations.append(
                    f"工序 {task_codes.get(tid, tid)} 的开始时间早于依赖约束"
                )
            start[tid] = max(computed, fixed)
        else:
            start[tid] = computed
        end[tid] = start[tid] + duration

    critical_duration = max(end.values()) if end else 0.0
    return PlanScheduleResult(
        schedule={tid: (start[tid], end[tid]) for tid in task_ids},
        critical_duration=critical_duration,
        violations=violations,
    )


def cast_id(value: int | None) -> int:
    """把可能为 None 的主键断言为 int（工具内部使用）。"""
    assert value is not None
    return value


__all__ = ["PlanScheduleResult", "schedule_plan"]
