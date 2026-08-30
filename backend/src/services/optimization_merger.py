"""Pareto 解集合并服务。

将多个优化运行（不同 Task 拓扑）的 Pareto 解合并为单一非支配前缘，
用于跨拓扑结果的对比分析。仅做纯计算，不写数据库。

合并前提：
1. 所有参与合并的解属于同一目标空间（cost/emission/duration 均最小化）。
2. 各运行覆盖的任务 id 集合必须一致，否则无法横向比较 strategies，
   此时抛出 ValueError（router 转 422）。
"""

from src.models.optimize import ParetoSolution
from src.schemas.optimize import TaskStrategy

DEDUP_DECIMALS = 6


def _task_ids_of(solution: ParetoSolution) -> set[int]:
    """提取某个解覆盖的任务 id 集合。"""
    strategies: list[TaskStrategy] = solution.strategies or []
    return {s.task_id for s in strategies}


def _sorted_task_ids(solutions: list[ParetoSolution]) -> list[int]:
    """按排序后的 task_id 元组确定一个运行的任务集合（用于一致性比较）。"""
    if not solutions:
        return []
    return sorted(_task_ids_of(solutions[0]))


def _same_objective_tuple(a: ParetoSolution, b: ParetoSolution) -> bool:
    """目标空间近似相等（防浮点误差），用于剔除重复解。"""
    return (
        round(a.cost, DEDUP_DECIMALS) == round(b.cost, DEDUP_DECIMALS)
        and round(a.emission, DEDUP_DECIMALS) == round(b.emission, DEDUP_DECIMALS)
        and round(a.duration, DEDUP_DECIMALS) == round(b.duration, DEDUP_DECIMALS)
    )


def _dominates(a: ParetoSolution, b: ParetoSolution) -> bool:
    """判断解 a 是否支配解 b（三目标均为最小化）。

    a 支配 b 当且仅当 a 在所有目标上不劣于 b，且至少一个目标严格更优。
    """
    no_worse = (
        a.cost <= b.cost and a.emission <= b.emission and a.duration <= b.duration
    )
    strictly_better = (
        a.cost < b.cost or a.emission < b.emission or a.duration < b.duration
    )
    return no_worse and strictly_better


def validate_task_set_consistency(run_task_sets: dict[object, list[int]]) -> None:
    """校验各运行的任务 id 集合一致。

    Args:
        run_task_sets: {run_id: 排序后的 task_id 列表}，来源可以是
            持久化的运行快照（推荐）或解的策略列表。

    Raises:
        ValueError: 存在运行的任务集合与其他运行不一致时抛出，消息含具体 run_id。
    """
    signatures = {run_id: sig for run_id, sig in run_task_sets.items() if sig}
    if not signatures:
        return
    reference_id, reference = next(iter(signatures.items()))
    inconsistent = [run_id for run_id, sig in signatures.items() if sig != reference]
    if inconsistent:
        mismatch = ", ".join(str(r) for r in [reference_id, *inconsistent])
        raise ValueError(f"各优化运行的任务 id 集合不一致，无法合并比较: {mismatch}")


def validate_task_consistency(
    solutions_by_run: dict[object, list[ParetoSolution]],
) -> None:
    """校验各运行的任务 id 集合一致（从解的策略列表推导任务集）。

    与 :func:`validate_task_set_consistency` 等价，作为快照校验的兜底。
    """
    validate_task_set_consistency({
        run_id: _sorted_task_ids(sols) for run_id, sols in solutions_by_run.items()
    })


def merge_pareto_solutions(
    solutions: list[ParetoSolution],
) -> list[ParetoSolution]:
    """合并多个运行的 Pareto 解，返回非支配前缘。

    - 按目标空间近似相等去重（复用 nsga2 近似去重思路）。
    - 剔除被其它解（含跨运行）支配的解。
    - 输出保持输入的稳定顺序。

    Args:
        solutions: 来自一个或多个运行的 ParetoSolution 列表。

    Returns:
        非支配子集（未被任何解支配的 Pareto 前缘）。
    """
    # 1. 按 run 分组并校验任务集一致性
    solutions_by_run: dict[object, list[ParetoSolution]] = {}
    for sol in solutions:
        solutions_by_run.setdefault(sol.run_id, []).append(sol)
    validate_task_consistency(solutions_by_run)

    # 2. 目标空间近似去重（保留先出现者，保持原序）
    unique: list[ParetoSolution] = []
    for sol in solutions:
        if any(_same_objective_tuple(sol, kept) for kept in unique):
            continue
        unique.append(sol)

    # 3. 两两支配过滤，保留非支配解
    result: list[ParetoSolution] = []
    for i, sol in enumerate(unique):
        if any(_dominates(other, sol) for j, other in enumerate(unique) if j != i):
            continue
        result.append(sol)

    return result
