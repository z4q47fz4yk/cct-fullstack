from typing import Sequence, TypedDict

from src.models.task import Task, TaskDependency


class TaskSchedule(TypedDict):
    """单个任务的时间安排"""

    es: float  # 最早开始
    ef: float  # 最早结束
    ls: float  # 最晚开始
    lf: float  # 最晚结束
    float: float  # 总浮动时间


class CriticalPathResult(TypedDict):
    """关键路径计算结果"""

    critical_task_ids: set[int]
    critical_duration: float
    task_schedules: dict[int, TaskSchedule]


def calculate_critical_path(
    tasks: Sequence[Task],
    dependencies: Sequence[TaskDependency],
) -> CriticalPathResult:
    """计算关键路径（纯工具函数）

    使用 CPM (Critical Path Method) 算法：
    1. 拓扑排序所有任务
    2. 前向传递: 计算每个任务的最早开始/结束时间 (ES, EF)
    3. 后向传递: 计算每个任务的最晚开始/结束时间 (LS, LF)
    4. 关键路径: 总浮动时间为0的任务 (ES == LS 或 EF == LF)

    Args:
        tasks: 任务列表
        dependencies: 依赖关系列表

    Returns:
        CriticalPathResult: 包含关键任务ID、关键路径工期和任务时间安排
    """
    if not tasks:
        return {
            "critical_task_ids": set(),
            "critical_duration": 0.0,
            "task_schedules": {},
        }

    # 构建任务字典: task_id -> duration
    task_durations: dict[int, float] = {}
    for t in tasks:
        assert t.id is not None
        task_durations[t.id] = t.duration
    task_ids = set(task_durations.keys())

    deps = dependencies

    # 构建依赖图结构
    # predecessors: task_id -> list of (predecessor_id, type)
    predecessors: dict[int, list[tuple[int, str]]] = {t: [] for t in task_ids}
    # successors: task_id -> list of (successor_id, type)
    successors: dict[int, list[tuple[int, str]]] = {t: [] for t in task_ids}

    for dep in deps:
        if dep.task_id in task_ids and dep.predecessor_id in task_ids:
            predecessors[dep.task_id].append((dep.predecessor_id, dep.type))
            successors[dep.predecessor_id].append((dep.task_id, dep.type))

    # 拓扑排序 (Kahn算法)
    in_degree = {t: len(predecessors[t]) for t in task_ids}
    queue = [t for t in task_ids if in_degree[t] == 0]
    topo_order: list[int] = []

    while queue:
        current = queue.pop(0)
        topo_order.append(current)
        for succ, _ in successors[current]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # 如果拓扑排序失败（存在循环），返回空结果
    if len(topo_order) != len(task_ids):
        # 存在循环依赖，无法计算关键路径
        return {
            "critical_task_ids": set(),
            "critical_duration": 0.0,
            "task_schedules": {},
        }

    # 前向传递: 计算 ES (最早开始), EF (最早结束)
    es: dict[int, float] = dict.fromkeys(task_ids, 0.0)  # 最早开始时间
    ef: dict[int, float] = dict.fromkeys(task_ids, 0.0)  # 最早结束时间

    for task_id in topo_order:
        duration = task_durations[task_id]
        preds = predecessors[task_id]

        if not preds:
            # 没有前置任务，从0开始
            es[task_id] = 0.0
        else:
            # 根据依赖类型计算当前任务的最早开始时间。
            max_start = 0.0
            for pred_id, dep_type in preds:
                pred_ef = ef[pred_id]
                if dep_type == "FS":
                    start_time = pred_ef
                elif dep_type == "SS":
                    start_time = es[pred_id]
                elif dep_type == "FF":
                    # FF: 当前任务的EF = 前置任务的EF
                    # 这意味着当前任务的开始时间需要调整
                    start_time = pred_ef - duration
                else:
                    start_time = pred_ef

                max_start = max(max_start, start_time)
            es[task_id] = max_start

        ef[task_id] = es[task_id] + duration

    # 项目总工期 = 最大 EF
    project_duration = max(ef.values()) if ef else 0.0

    # 后向传递: 计算 LS (最晚开始), LF (最晚结束)
    ls: dict[int, float] = dict.fromkeys(task_ids, project_duration)  # 最晚开始时间
    lf: dict[int, float] = dict.fromkeys(task_ids, project_duration)  # 最晚结束时间

    # 反向遍历拓扑排序
    for task_id in reversed(topo_order):
        duration = task_durations[task_id]
        succs = successors[task_id]

        if not succs:
            # 没有后继任务，LF = 项目总工期
            lf[task_id] = project_duration
        else:
            # LF = min(后继任务约束下的最晚完成时间)
            min_finish = project_duration
            for succ_id, dep_type in succs:
                succ_ls = ls[succ_id]
                if dep_type == "FS":
                    finish_time = succ_ls
                elif dep_type == "SS":
                    # SS: 当前任务的 LS = 后继任务的 LS。
                    finish_time = succ_ls + duration
                elif dep_type == "FF":
                    finish_time = lf[succ_id]
                else:
                    finish_time = succ_ls

                min_finish = min(min_finish, finish_time)
            lf[task_id] = min_finish

        ls[task_id] = lf[task_id] - duration

    # 计算关键路径: 总浮动时间为0的任务 (ES == LS)
    critical_task_ids: set[int] = set()
    task_schedules: dict[int, TaskSchedule] = {}

    for task_id in task_ids:
        total_float = ls[task_id] - es[task_id]
        task_schedules[task_id] = {
            "es": es[task_id],
            "ef": ef[task_id],
            "ls": ls[task_id],
            "lf": lf[task_id],
            "float": total_float,
        }
        # 关键任务: 总浮动时间为0 (或接近0，考虑浮点精度)
        if abs(total_float) < 0.001:
            critical_task_ids.add(task_id)

    return {
        "critical_task_ids": critical_task_ids,
        "critical_duration": project_duration,
        "task_schedules": task_schedules,
    }


__all__ = ["calculate_critical_path"]
