"""
NSGA2 多目标优化模块

用于多目标项目调度优化，支持成本、碳排放、工期三个目标的帕累托最优解求解。

算法核心使用 pymoo 库。
"""

from __future__ import annotations

import datetime as dt
import math
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Literal, Optional

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.callback import Callback
from pymoo.core.problem import Problem
from pymoo.optimize import minimize

# ============================================================================
# 数据类型
# ============================================================================


@dataclass
class TaskInput:
    """任务输入

    Args:
        id: 任务ID
        code: 任务编码
        duration: 工期（天）
    """

    id: int
    code: str
    duration: float


@dataclass
class DependencyInput:
    """依赖关系输入

    Args:
        predecessor_id: 前置任务ID
        task_id: 当前任务ID
        type: 依赖类型（FS/SS/FF）
    """

    predecessor_id: int
    task_id: int
    type: str = "FS"


@dataclass
class ResourceUsageInput:
    """资源使用量输入

    注意：quantity 应该是该任务对指定资源的总用量（总量），
    算法内部会根据工期分配到每一天。

    Args:
        task_id: 任务ID
        resource_id: 资源ID
        quantity: 该任务对该资源的总用量
    """

    task_id: int
    resource_id: int
    quantity: float


@dataclass
class ResourceCostInfo:
    """资源成本信息

    Args:
        category: 资源类别
            - material: 材料
            - mechanical: 机械
            - labor: 人工
            - transport: 运输
        unit_price: 单价
        carbon_factor: 碳排放因子
    """

    category: str
    unit_price: float
    carbon_factor: float


@dataclass
class NSGA2Config:
    """NSGA2 算法配置

    Args:
        pop_size: 种群大小，默认 200
        n_generations: 进化代数，默认 200
        seed: 随机种子，默认 1
    """

    pop_size: int = 200
    n_generations: int = 200
    seed: int = 1


@dataclass
class OptimizationRequest:
    """优化请求

    Args:
        session_id: 优化会话ID，用于回调标识
        tasks: 任务列表
        dependencies: 依赖关系列表
        resource_usages: 资源使用量列表（每个任务的每种资源总用量）
        resource_costs: 资源成本信息映射 {resource_id: ResourceCostInfo}
        resource_constraints: 资源日用量上限约束 {resource_id: max_daily_usage}
        personnel_living_carbon_factor: 人员生活碳排放因子
        discount_rate: 月折现率，默认 0.05/12
        accelerated_ratio: 加速工期比例，加速施工时工期 × 此比例，默认 0.8
        max_offset: 最大开始时间偏移量（天），默认 3
        nsga2_config: NSGA2 算法配置
        labor_by_task_idx: 每个任务的 labor 总工日（用于 peak_personnel 派生）
        housing_enabled: 是否配置临时用房（项目 housing_resource_id 已设置）。
            与 housing_resource_carbon_factor 解耦：碳因子为 0 只表示用房排放为 0，
            不影响房间数派生。
        housing_resource_carbon_factor: 临时用房碳排放因子（0 表示无用房排放）
        housing_resource_max_reuses: 临时用房最大周转次数
        housing_resource_reuse_count: 临时用房实际周转次数
        housing_safety_factor: 临时用房安全系数
        persons_per_room: 每间临时用房人数
    """

    session_id: str
    tasks: List[TaskInput]
    dependencies: List[DependencyInput]
    resource_usages: List[ResourceUsageInput]
    resource_costs: Dict[int, ResourceCostInfo]
    resource_constraints: Dict[int, float]
    personnel_living_carbon_factor: float
    discount_rate: float = 0.05 / 12
    accelerated_ratio: float = 0.8
    max_offset: int = 3
    nsga2_config: Optional[NSGA2Config] = None
    labor_by_task_idx: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    housing_enabled: bool = False
    housing_resource_carbon_factor: float = 0.0
    housing_resource_max_reuses: int = 1
    housing_resource_reuse_count: int = 1
    housing_safety_factor: float = 1.2
    persons_per_room: int = 4
    # 现值折现的日历锚点（自然月结算用）；None 时退回旧 30 天结算口径
    anchor_date: Optional[dt.date] = None


@dataclass
class SolutionOutput:
    """单个帕累托解

    Args:
        solution_id: 解序号
        modes: 每个任务的施工模式 [0=标准, 1=加速, 2=低碳, 3=加速低碳]
        offsets: 每个任务的开始时间偏移（天）
        starts: 每个任务的最早开始时间（天）
        cost: 现值成本
        emission: 碳排放总量
        duration: 总工期（天）
        violations: 资源约束违反量 {resource_id: violation_amount}
        peak_personnel: 峰值施工人数
        housing_rooms: 临时用房间数
    """

    solution_id: int
    modes: List[int]
    offsets: List[int]
    starts: List[float]
    cost: float
    emission: float
    duration: float
    violations: Dict[int, float]
    peak_personnel: int = 0
    housing_rooms: int = 0


@dataclass
class OptimizationResult:
    """优化结果

    Args:
        session_id: 优化会话ID
        status: 运行状态 "completed" 或 "failed"
        solutions: 帕累托解列表
        error_message: 错误信息（仅在失败时有值）
    """

    session_id: str
    status: Literal["completed", "failed"]
    solutions: List[SolutionOutput]
    error_message: Optional[str] = None


class OptimizationAborted(Exception):
    """优化被主动中断（PATCH /optimize/{id} 触发）。

    在 pymoo 回调（每代检查）或 run_optimization 入口检测到中断标记时抛出，
    由 run_optimization 捕获后以失败结果（error_message="优化已被用户中断"）走回调通道。
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"优化会话 {session_id} 已被用户中断")


# ============================================================================
# 回调接口
# ============================================================================


class ProgressCallback(ABC):
    """优化进度回调接口

    使用者实现此接口以接收优化进度和结果。
    所有回调方法由同步线程调用，不应在回调中执行阻塞操作。
    """

    @abstractmethod
    def on_progress(
        self, session_id: str, current_generation: int, total_generations: int
    ) -> None:
        """每代优化完成后调用

        Args:
            session_id: 优化会话标识
            current_generation: 当前代数 (1 ~ n_generations)
            total_generations: 总代数
        """
        pass

    @abstractmethod
    def on_complete(self, result: OptimizationResult) -> None:
        """优化完成后调用

        Args:
            result: 优化结果
        """
        pass


# ============================================================================
# 算法核心
# ============================================================================

# 资源类别在成本/排放矩阵中的列索引
_CATEGORY_INDEX = {
    "material": 0,
    "mechanical": 1,
    "personnel_construction": 2,
    "personnel_living": 3,
    "transport": 4,
}


def compute_total_time(
    durations: List[float],
    start_offsets: List[int],
    in_degree: Dict[int, int],
    graph: Dict[int, List[tuple[int, str]]],
    task_ids: List[int],
    task_id_to_idx: Dict[int, int],
) -> tuple[float, Dict[int, float]]:
    """
    根据任务工期和开始偏移计算总工期和每个任务的最早开始时间。

    使用拓扑排序处理依赖关系（依赖关系不含 lag）。

    Args:
        durations: 每个任务（按 task_ids 顺序）的工期
        start_offsets: 每个任务（按 task_ids 顺序）的开始偏移（天）
        in_degree: 每个任务的入度
        graph: 邻接表 {predecessor_id: [(successor_id, dependency_type), ...]}
        task_ids: 任务ID列表
        task_id_to_idx: 任务ID到索引的映射

    Returns:
        (total_duration, earliest_start_dict)
        - total_duration: 总工期（天）
        - earliest_start_dict: {task_id: earliest_start} 每个任务的最早开始时间
    """
    in_deg = in_degree.copy()
    earliest_start: Dict[int, float] = {}
    queue: deque[int] = deque([tid for tid in task_ids if in_deg[tid] == 0])

    for tid in queue:
        earliest_start[tid] = start_offsets[task_id_to_idx[tid]]

    processed: set[int] = set(queue)

    while queue:
        current = queue.popleft()
        for succ, dependency_type in graph[current]:
            pred_start = earliest_start[current]
            pred_finish = earliest_start[current] + durations[task_id_to_idx[current]]
            successor_duration = durations[task_id_to_idx[succ]]
            successor_offset = start_offsets[task_id_to_idx[succ]]

            # 不同依赖类型只改变前置时间点。
            if dependency_type == "SS":
                es = pred_start + successor_offset
            elif dependency_type == "FF":
                es = pred_finish - successor_duration + successor_offset
            else:
                # FS 以及未知类型保持原有行为。
                es = pred_finish + successor_offset

            if succ not in earliest_start or es > earliest_start[succ]:
                earliest_start[succ] = es
            in_deg[succ] -= 1
            if in_deg[succ] == 0 and succ not in processed:
                processed.add(succ)
                queue.append(succ)

    total_time = max(
        (earliest_start[tid] + durations[task_id_to_idx[tid]]) for tid in task_ids
    )
    return total_time, earliest_start


def calculate_present_value(
    t_s: int,
    t_e: int,
    C: float,
    r: float = 0.05 / 12,
    anchor: dt.date | None = None,
) -> float:
    """
    计算施工成本的现值。

    采用月结算方式：传入 anchor 时按自然月末结算（锚点所在自然月为第 1 期），
    否则退回旧口径每 30 天结算一次（仅兼容旧调用/旧测试）。使用 IRR 折现率。

    Args:
        t_s: 开始时间（天）
        t_e: 结束时间（天）
        C: 总成本
        r: 月折现率
        anchor: 折现锚点日期；None 时使用旧 30 天结算口径

    Returns:
        成本的现值
    """
    D = t_e - t_s
    if D <= 0:
        return C

    if anchor is not None:
        start_date = anchor + dt.timedelta(days=t_s)
        # end 为开区间（与旧口径 period_end 语义一致）
        end_date = anchor + dt.timedelta(days=t_e)
        if end_date <= start_date:
            return C

        pv = 0.0
        k = 1
        cursor = dt.date(anchor.year, anchor.month, 1)
        while cursor < end_date:
            month_start = max(start_date, cursor)
            if cursor.month == 12:
                next_cursor = dt.date(cursor.year + 1, 1, 1)
            else:
                next_cursor = dt.date(cursor.year, cursor.month + 1, 1)
            month_end = min(end_date, next_cursor)
            delta_t = (month_end - month_start).days
            if delta_t > 0:
                cost_ratio = delta_t / D
                discount_factor = 1 / ((1 + r) ** k)
                pv += C * cost_ratio * discount_factor
            cursor = next_cursor
            k += 1

        if pv > 0 and C / pv >= 1.7:
            print("[INFO]: ts =", t_s, ", t_e =", t_e, ", r =", r, ", C =", C)
            print("[WARN]: C / pv =", C / pv)
        return pv

    # TODO: 旧 30 天结算口径仅保留给无锚点的直接调用；新数据全部走自然月分支。
    first_settlement = math.ceil(t_s / 30) * 30
    pv = 0.0
    k = 1

    for t_k in range(int(first_settlement), int(max(t_e, first_settlement)) + 30, 30):
        period_start = max(t_s, t_k - 30)
        period_end = min(t_e, t_k)
        delta_t = period_end - period_start
        if delta_t <= 0:
            continue
        cost_ratio = delta_t / D
        discount_factor = 1 / ((1 + r) ** k)
        pv += C * cost_ratio * discount_factor
        k += 1

    # 零成本任务（C=0）时 pv 恒为 0，跳过该调试检查避免 0/0 产生
    # RuntimeWarning（np.float64(0) / 0.0 = nan）
    if pv > 0 and C / pv >= 1.7:
        print("[INFO]: ts =", t_s, ", t_e =", t_e, ", r =", r, ", C =", C)
        print("[WARN]: C / pv =", C / pv)

    return pv


def get_adjusted_durations_vectorized(
    T_N: np.ndarray, modes: np.ndarray, accelerated_ratio: float
) -> np.ndarray:
    """
    向量化版本：根据模式数组调整工期数组。

    模式 0,2: 工期不变
    模式 1,3: 工期 × accelerated_ratio

    Args:
        T_N: 原始工期数组
        modes: 模式数组（0-3）
        accelerated_ratio: 加速工期比例

    Returns:
        调整后的工期数组
    """
    return np.where(modes % 2 == 0, T_N, accelerated_ratio * T_N)


def get_mode_multipliers_vectorized(
    T_N: np.ndarray,
    T_G: np.ndarray,
    modes: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    向量化版本：获取所有任务的成本乘数和排放乘数矩阵。

    成本/排放矩阵的列顺序：material, mechanical, personnel_construction,
    personnel_living, transport

    Args:
        T_N: 原始工期数组
        T_G: 调整后工期数组
        modes: 模式数组

    Returns:
        (cost_multipliers, emission_multipliers)
    """
    n_tasks = len(modes)
    cost_mults = np.ones((n_tasks, 5), dtype=np.float64)
    emission_mults = np.ones((n_tasks, 5), dtype=np.float64)

    # 模式 1: 加速施工
    # 成本：机械设备 +50%×ΔT/T，人工 +50%×ΔT/T，生活人员 -ΔT/T
    # 排放：机械设备正常，生活人员 × T_G/T_N（工期缩短则人员生活碳排减少）
    mask_acc = modes == 1
    if np.any(mask_acc):
        delta = (T_N[mask_acc] - T_G[mask_acc]) / T_N[mask_acc]
        cost_mults[mask_acc, 1] = 1 + 1.5 * delta  # mechanical
        cost_mults[mask_acc, 2] = 1 + 1.5 * delta  # personnel_construction
        cost_mults[mask_acc, 3] = 1 - delta  # personnel_living
        emission_mults[mask_acc, 3] = T_G[mask_acc] / T_N[mask_acc]  # personnel_living

    # 模式 2: 低碳施工
    # 成本：机械设备 +20%
    # 排放：机械设备 -40%，人工 -40%
    mask_lc = modes == 2
    if np.any(mask_lc):
        cost_mults[mask_lc, 1] = 1.2  # mechanical
        emission_mults[mask_lc, 1] = 0.6  # mechanical
        emission_mults[mask_lc, 2] = 0.6  # personnel_construction

    # 模式 3: 加速且低碳
    # 成本：机械设备 1.2×(1+1.5×ΔT/T)，人工 +50%×ΔT/T，生活人员 -ΔT/T
    # 排放：机械设备 -40%，人工 -40%，生活人员 × T_G/T_N
    mask_acc_lc = modes == 3
    if np.any(mask_acc_lc):
        delta = (T_N[mask_acc_lc] - T_G[mask_acc_lc]) / T_N[mask_acc_lc]
        cost_mults[mask_acc_lc, 1] = 1.2 * (1 + 1.5 * delta)  # mechanical
        cost_mults[mask_acc_lc, 2] = 1 + 1.5 * delta  # personnel_construction
        cost_mults[mask_acc_lc, 3] = 1 - delta  # personnel_living
        emission_mults[mask_acc_lc, 1] = 0.6  # mechanical
        emission_mults[mask_acc_lc, 2] = 0.6  # personnel_construction
        emission_mults[mask_acc_lc, 3] = (
            T_G[mask_acc_lc] / T_N[mask_acc_lc]
        )  # personnel_living

    return cost_mults, emission_mults


def calculate_resource_violations_vectorized(
    durations: np.ndarray,
    earliest_starts: np.ndarray,
    resource_usage_matrix: np.ndarray,
    resource_constraints: np.ndarray,
) -> np.ndarray:
    """
    向量化计算每个资源约束的违反量。

    将每个任务的总用量按工期平均分配到每一天，
    然后统计每天每个资源的最大使用量，与约束比较得到违反量。

    对 earliest_starts / durations 向上取整（math.ceil）为天数索引，
    避免加速任务（T_G < 1 天）被 int() 截断到 0 而跳过资源计入。

    注（C-3 复核：非 bug，属有意行为）：本函数以「调整后工期」durations（即 T_G）
    为除数把总用量均摊到每天。因此加速施工（模式 1/3，T_G < T_N）会使该任务对受
    约束资源的日用量密度「自动升高」——这与 get_mode_multipliers_vectorized 的成本
    模型语义一致：数量视为不变，仅成本/碳排乘数随模式变化，而约束判定反映的是
    「同样的总用量被压缩到更短工期」。注意受约束资源仅限已显式配置 resource_constraint、
    且该资源在该任务存在用量的列；其余资源的用量不参与约束判定。

    Args:
        durations: 每个任务的工期数组
        earliest_starts: 每个任务的最早开始时间数组
        resource_usage_matrix: 资源使用量矩阵 (n_tasks, n_resources)
            每行是一个任务，每列是一种资源，值为该任务对该资源的总量
        resource_constraints: 资源日用量上限数组 (n_resources,)

    Returns:
        违反量数组 (n_resources,)，只包含正值，零值表示未违反
    """
    n_tasks, n_resources = resource_usage_matrix.shape

    # 计算总工期
    # 加速模式下 T_G 可能为小数（如 0.8）；向上取整以保证 daily_usage 矩阵足够大
    total_time = int(math.ceil(np.max(earliest_starts + durations)))

    # 预分配每天每资源的用量矩阵
    daily_usage = np.zeros((total_time, n_resources), dtype=np.float64)

    # 填充任务时间矩阵
    # earliest_starts / durations 可能 <1（加速模式），向上取整为天数索引
    for task_idx in range(n_tasks):
        es = math.ceil(earliest_starts[task_idx])
        dur = math.ceil(durations[task_idx])
        if dur > 0:
            # 总量按工期平均分配到每天
            daily_rate = resource_usage_matrix[task_idx, :] / dur
            daily_usage[es : es + dur, :] += daily_rate

    # 计算每天的最大资源使用量
    max_daily_usage = daily_usage.max(axis=0)

    # 计算违反量：max(0, 实际最大日用量 - 约束上限)
    violations = np.maximum(0, max_daily_usage - resource_constraints)

    return violations


def _dedup_pareto_indices(F: np.ndarray, X: np.ndarray, decimals: int = 6) -> list[int]:
    """根据目标空间（cost, emission, duration）近似相等去重 pymoo 输出。

    pymoo NSGA2 的 eliminate_duplicates=True 仅按决策变量 X 精确相等去重，
    但多个不同的 mode/offset 组合可能映射到相同的 (cost, emission, duration)。
    本函数先按目标空间去重，再按 X 去重（同 F 但不同 X 的罕见重复一并去掉），
    返回保留行在原数组中的下标（保持 pymoo 原序）。

    Args:
        F: pymoo 输出的目标空间矩阵 (n, 3)
        X: pymoo 输出的决策空间矩阵 (n, n_var)
        decimals: 目标值的舍入位数（防浮点误差）

    Returns:
        保留行的下标列表（已按 pymoo 原序排序）
    """
    F_round = np.round(np.asarray(F, dtype=np.float64), decimals=decimals)
    X_int = np.asarray(X, dtype=np.int64)
    _, first_idx = np.unique(F_round, axis=0, return_index=True)
    first_idx = np.sort(first_idx)  # 恢复 pymoo 原序
    seen_x: set[tuple[int, ...]] = set()
    final_idx: list[int] = []
    for k in first_idx:
        key = tuple(X_int[k].tolist())
        if key in seen_x:
            continue
        seen_x.add(key)
        final_idx.append(k)
    return final_idx


class ConstructionProblem(Problem):
    """
    施工作业计划优化问题定义。

    决策变量：
    - 前 n_var/2 个：每个任务的施工模式（0-3 的整数）
    - 后 n_var/2 个：每个任务的开始时间偏移（0-max_offset 的整数）

    目标函数：
    - f1: 现值成本（最小化）
    - f2: 碳排放总量（最小化）
    - f3: 总工期（最小化）

    约束：
    - 每个资源日用量不超过约束上限
    """

    def __init__(
        self,
        n_tasks: int,
        task_ids: List[int],
        base_costs_matrix: np.ndarray,
        base_emissions_matrix: np.ndarray,
        task_id_to_duration: Dict[int, float],
        base_resource_usage_matrix: np.ndarray,
        resource_constraints: np.ndarray,
        in_degree: Dict[int, int],
        graph: Dict[int, List[tuple[int, str]]],
        task_id_to_idx: Dict[int, int],
        max_start_offset: int = 60,
        discount_rate: float = 0.05 / 12,
        accelerated_ratio: float = 0.8,
        anchor_date: Optional[dt.date] = None,
        labor_by_task_idx: np.ndarray | None = None,
        housing_enabled: bool = False,
        housing_resource_carbon_factor: float = 0.0,
        housing_resource_max_reuses: int = 1,
        housing_resource_reuse_count: int = 1,
        housing_safety_factor: float = 1.2,
        persons_per_room: int = 4,
        **kwargs,
    ):
        """
        初始化优化问题。

        Args:
            n_tasks: 任务数量
            task_ids: 任务ID列表
            base_costs_matrix: 基础成本矩阵 (n_tasks, 5)
            base_emissions_matrix: 基础排放矩阵 (n_tasks, 5)
            task_id_to_duration: 任务ID到工期的映射
            base_resource_usage_matrix: 资源使用量矩阵 (n_tasks, n_resources)
            resource_constraints: 资源约束上限 (n_resources,)
            in_degree: 入度字典
            graph: 邻接表
            task_id_to_idx: 任务ID到索引的映射
            max_start_offset: 最大开始偏移
            discount_rate: 月折现率
            accelerated_ratio: 加速工期比例
            labor_by_task_idx: 每个任务的 labor 总工日（用于 peak_personnel 派生）
            housing_enabled: 是否配置临时用房（项目 housing_resource_id 已设置）。
                与 carbon_factor 解耦：因子为 0 只表示用房排放为 0，不影响房间数派生。
            housing_resource_carbon_factor: 临时用房碳排放因子（0 表示无用房排放）
            housing_resource_max_reuses: 临时用房最大周转次数
            housing_resource_reuse_count: 临时用房实际周转次数
            housing_safety_factor: 临时用房安全系数
            persons_per_room: 每间临时用房人数
        """
        super().__init__(
            n_var=n_tasks * 2,
            n_obj=3,
            n_constr=len(resource_constraints),
            xl=np.array([0] * n_tasks + [0] * n_tasks),
            xu=np.array([4] * n_tasks + [max_start_offset] * n_tasks),
            type_var=int,
            **kwargs,
        )
        self.n_tasks = n_tasks
        self.task_ids = task_ids
        self.base_costs_matrix = base_costs_matrix
        self.base_emissions_matrix = base_emissions_matrix
        self.task_id_to_duration = task_id_to_duration
        self.base_resource_usage_matrix = base_resource_usage_matrix
        self.resource_constraints = resource_constraints
        self.in_degree = in_degree
        self.graph = graph
        self.task_id_to_idx = task_id_to_idx
        self.max_start_offset = max_start_offset
        self.discount_rate = discount_rate
        self.accelerated_ratio = accelerated_ratio
        self.anchor_date = anchor_date

        # 预计算原始工期数组
        self.base_durations = np.array(
            [task_id_to_duration[tid] for tid in task_ids], dtype=np.float64
        )

        # housing 配置
        self.labor_by_task_idx = (
            labor_by_task_idx
            if labor_by_task_idx is not None
            else np.zeros(n_tasks, dtype=np.float64)
        )
        self.housing_enabled = housing_enabled
        self.housing_resource_carbon_factor = housing_resource_carbon_factor
        self.housing_resource_max_reuses = housing_resource_max_reuses
        self.housing_resource_reuse_count = housing_resource_reuse_count
        self.housing_safety_factor = housing_safety_factor
        self.persons_per_room = persons_per_room

    def _compute_housing_rooms(self, peak_personnel: int) -> int:
        """计算临时用房间数

        由峰值施工人数派生：ceil(peak_personnel × 安全系数 / 每间人数)。
        是否计算由 housing_enabled 决定，与碳因子解耦——碳因子为 0 只表示
        用房排放为 0，不应让房间数消失（修复：峰值 26 人、碳因子 0 时房间数为 0）。

        Args:
            peak_personnel: 峰值施工人数

        Returns:
            临时用房间数
        """
        if not self.housing_enabled or self.persons_per_room <= 0:
            return 0
        return math.ceil(
            peak_personnel * self.housing_safety_factor / self.persons_per_room
        )

    def _compute_peak_personnel(
        self, T_G: np.ndarray, earliest_starts: np.ndarray
    ) -> int:
        """计算每个解的 peak_personnel（峰值施工人数）

        通过 labor_by_task_idx（总工日）和 T_G（调整后工期）计算日均用工，
        在时间窗上累加得到每天的用工人数，取最大值。

        内部对 earliest_starts + T_G 向上取整为天数索引（math.ceil）。这一选择与
        calculate_resource_violations_vectorized 保持一致；它意味着：加速任务
        （T_G < 1 天）会被向上取整为 1 天，少量低估实际峰值（约 1/0.8 = 1.25 倍
        的"按天"窗口），但避免了 int() 截断导致加速任务的用工被完全忽略。

        Args:
            T_G: 调整后工期数组
            earliest_starts: 最早开始时间数组

        Returns:
            峰值施工人数
        """
        if self.labor_by_task_idx.sum() == 0:
            return 0
        # max_end 的矩阵大小也向上取整，避免与 total_time 不一致
        max_end = math.ceil(
            max(es + tg for es, tg in zip(earliest_starts, T_G, strict=True))
        )
        if max_end <= 0:
            return 0
        daily = np.zeros(max_end + 1)
        for i in range(self.n_tasks):
            total = self.labor_by_task_idx[i]
            if total <= 0 or T_G[i] <= 0:
                continue
            avg_daily = total / T_G[i]  # 日均用工
            start = math.ceil(earliest_starts[i])
            end = math.ceil(start + T_G[i])
            if end > start:
                daily[start:end] += avg_daily
        return int(daily.max())

    def _evaluate(
        self, x: np.ndarray, out: dict[Literal["F", "G"], np.ndarray], *args, **kwargs
    ) -> None:
        """
        评估一组解的目标函数值和约束违反量。

        Args:
            x: 决策变量矩阵 (pop_size, n_var)
            out: 输出字典，包含 'F'（目标函数值）和 'G'（约束违反量）
        """
        f1: List[float] = []
        f2: List[float] = []
        f3: List[float] = []
        G: List[np.ndarray] = []

        for xi in x:
            xi_int = xi.astype(int)
            modes = xi_int[: self.n_tasks]
            offsets = xi_int[self.n_tasks :]

            # 调整后工期
            T_G = get_adjusted_durations_vectorized(
                self.base_durations, modes, self.accelerated_ratio
            )

            # 成本乘数和排放乘数
            cost_mults, emission_mults = get_mode_multipliers_vectorized(
                self.base_durations, T_G, modes
            )

            # 成本和排放
            task_costs = np.sum(self.base_costs_matrix * cost_mults, axis=1)
            task_emissions = np.sum(self.base_emissions_matrix * emission_mults, axis=1)
            total_emission = float(np.sum(task_emissions))

            # 计算总工期和最早开始时间
            total_time, earliest_starts = compute_total_time(
                T_G.tolist(),
                offsets.tolist(),
                self.in_degree,
                self.graph,
                self.task_ids,
                self.task_id_to_idx,
            )

            earliest_starts_array = np.array(
                [earliest_starts[tid] for tid in self.task_ids], dtype=np.float64
            )

            # 现值成本
            # es/ee 向上取整为天数，与 calculate_resource_violations_vectorized 一致；
            # 否则 int() 截断让加速任务 D=0，PV 直接返回 C（未折现）
            pv_cost = 0.0
            for i, task_id in enumerate(self.task_ids):
                es = earliest_starts[task_id]
                ee = es + T_G[i]
                pv_cost += calculate_present_value(
                    math.ceil(es),
                    math.ceil(ee),
                    task_costs[i],
                    self.discount_rate,
                    self.anchor_date,
                )

            # peak_personnel 与 housing
            peak_personnel = self._compute_peak_personnel(T_G, earliest_starts_array)
            housing_rooms = self._compute_housing_rooms(peak_personnel)
            if self.housing_enabled:
                divisor = max(1, self.housing_resource_max_reuses) * max(
                    1, self.housing_resource_reuse_count
                )
                total_emission += housing_rooms * (
                    self.housing_resource_carbon_factor / divisor
                )

            f1.append(pv_cost)
            f2.append(total_emission)
            f3.append(total_time)

            # 资源约束违反
            violations = calculate_resource_violations_vectorized(
                T_G,
                earliest_starts_array,
                self.base_resource_usage_matrix,
                self.resource_constraints,
            )
            G.append(violations)

        out["F"] = np.column_stack([f1, f2, f3])
        out["G"] = np.array(G)


class OptimizerCallback(Callback):
    """
    pymoo 回调适配器：将 pymoo 的 Callback 转换为 ProgressCallback。

    作为 ProgressCallback 的实现，接收 pymoo 的迭代事件，
    然后调用用户提供的 ProgressCallback。
    """

    def __init__(
        self,
        session_id: str,
        total_generations: int,
        callback: ProgressCallback,
        abort_event: Optional[threading.Event] = None,
    ):
        """
        初始化适配器。

        Args:
            session_id: 优化会话ID
            total_generations: 总代数
            callback: 用户实现的进度回调
            abort_event: 主动中断标记（线程安全），每代开始时检查，
                置位则抛出 OptimizationAborted 提前终止优化
        """
        super().__init__()
        self.session_id = session_id
        self.total_generations = total_generations
        self.callback = callback
        self.abort_event = abort_event

    def notify(self, algorithm) -> None:
        """pymoo 每代完成后调用此方法"""
        # 每代开始前检查中断标记：命中立即提前结束（协作式中止）
        if self.abort_event is not None and self.abort_event.is_set():
            raise OptimizationAborted(self.session_id)
        self.callback.on_progress(
            self.session_id, algorithm.n_gen, self.total_generations
        )


def build_problem(
    request: OptimizationRequest,
) -> tuple[ConstructionProblem, NSGA2Config]:
    """
    根据优化请求构建 pymoo 问题对象和算法配置。

    Args:
        request: 优化请求

    Returns:
        (problem, config) 元组
    """
    # 构建 task 映射
    task_ids = [t.id for t in request.tasks]
    task_id_to_idx = {tid: i for i, tid in enumerate(task_ids)}
    n_tasks = len(task_ids)

    # Duration: 直接从 tasks 获取
    task_id_to_duration = {t.id: t.duration for t in request.tasks}

    # 依赖图（依赖关系只保留类型，无 lag）
    graph: Dict[int, List[tuple[int, str]]] = defaultdict(list)
    in_degree: Dict[int, int] = defaultdict(int)
    for dep in request.dependencies:
        graph[dep.predecessor_id].append((dep.task_id, dep.type))
        in_degree[dep.task_id] += 1
    for tid in task_ids:
        if tid not in in_degree:
            in_degree[tid] = 0

    # 资源使用量矩阵
    resource_constraint_ids = list(request.resource_constraints.keys())
    resource_id_to_idx = {rid: idx for idx, rid in enumerate(resource_constraint_ids)}
    n_resources = len(resource_constraint_ids)
    base_resource_usage_matrix = np.zeros((n_tasks, n_resources), dtype=np.float64)

    for usage in request.resource_usages:
        if usage.task_id in task_id_to_idx and usage.resource_id in resource_id_to_idx:
            i = task_id_to_idx[usage.task_id]
            j = resource_id_to_idx[usage.resource_id]
            base_resource_usage_matrix[i, j] = usage.quantity

    # 成本和排放矩阵
    # 5 列: material, mechanical, personnel_construction, personnel_living, transport
    base_costs_matrix = np.zeros((n_tasks, 5), dtype=np.float64)
    base_emissions_matrix = np.zeros((n_tasks, 5), dtype=np.float64)

    # 计算每个任务的成本和排放
    # 需要记录 labor 资源的工日数用于计算 personnel_living 碳排放
    labor_quantities: Dict[int, float] = defaultdict(float)

    for usage in request.resource_usages:
        if usage.task_id not in task_id_to_idx:
            continue
        i = task_id_to_idx[usage.task_id]
        resource_info = request.resource_costs.get(usage.resource_id)
        if resource_info is None:
            continue

        cat = resource_info.category
        cost = resource_info.unit_price * usage.quantity
        emission = usage.quantity * resource_info.carbon_factor

        if cat == "material":
            base_costs_matrix[i, 0] += cost
            base_emissions_matrix[i, 0] += emission
        elif cat in ("machinery", "mechanical"):
            base_costs_matrix[i, 1] += cost
            base_emissions_matrix[i, 1] += emission
        elif cat == "labor":
            base_costs_matrix[i, 2] += cost  # personnel_construction
            base_emissions_matrix[i, 2] += emission
            # 记录 labor 工日数，用于计算 personnel_living 碳排放
            labor_quantities[usage.task_id] += usage.quantity
        elif cat == "transport":
            base_costs_matrix[i, 4] += cost
            base_emissions_matrix[i, 4] += emission

    # 计算 personnel_living 碳排放：工日数 × 人员生活碳排放因子
    for task_id, quantity in labor_quantities.items():
        i = task_id_to_idx[task_id]
        base_emissions_matrix[i, 3] = quantity * request.personnel_living_carbon_factor

    # 资源约束
    resource_constraints = np.array(
        [request.resource_constraints[rid] for rid in resource_constraint_ids],
        dtype=np.float64,
    )

    nsga2_config = request.nsga2_config or NSGA2Config()

    problem = ConstructionProblem(
        n_tasks=n_tasks,
        task_ids=task_ids,
        base_costs_matrix=base_costs_matrix,
        base_emissions_matrix=base_emissions_matrix,
        task_id_to_duration=task_id_to_duration,
        base_resource_usage_matrix=base_resource_usage_matrix,
        resource_constraints=resource_constraints,
        in_degree=dict(in_degree),
        graph=graph,
        task_id_to_idx=task_id_to_idx,
        max_start_offset=request.max_offset,
        discount_rate=request.discount_rate,
        accelerated_ratio=request.accelerated_ratio,
        anchor_date=request.anchor_date,
        labor_by_task_idx=request.labor_by_task_idx,
        housing_enabled=request.housing_enabled,
        housing_resource_carbon_factor=request.housing_resource_carbon_factor,
        housing_resource_max_reuses=request.housing_resource_max_reuses,
        housing_resource_reuse_count=request.housing_resource_reuse_count,
        housing_safety_factor=request.housing_safety_factor,
        persons_per_room=request.persons_per_room,
    )

    return problem, nsga2_config


def run_optimization(
    request: OptimizationRequest,
    callback: ProgressCallback,
    abort_event: Optional[threading.Event] = None,
) -> str:
    """
    启动 NSGA2 优化任务。

    同步阻塞运行，直到优化完成、出错或被主动中断。

    Args:
        request: 优化请求参数
        callback: 进度回调实现
        abort_event: 主动中断标记（线程安全），置位时每代检查并提前终止

    Returns:
        session_id

    Raises:
        Exception: 如果优化过程出错，会重新抛出（主动中断除外）
    """
    session_id = request.session_id

    # 构建问题
    problem, config = build_problem(request)

    # 创建算法
    algorithm = NSGA2(pop_size=config.pop_size, eliminate_duplicates=True)

    # 创建回调适配器
    opt_callback = OptimizerCallback(
        session_id, config.n_generations, callback, abort_event
    )

    # 执行优化
    try:
        # 启动竞态兜底：break 可能发生在任务 spawn 与引擎启动之间，
        # 入口处先查一次标记，置位则直接以中断结果退出。
        if abort_event is not None and abort_event.is_set():
            raise OptimizationAborted(session_id)

        res = minimize(
            problem,
            algorithm,
            ("n_gen", config.n_generations),
            seed=config.seed,
            callback=opt_callback,
            verbose=False,
        )
    except OptimizationAborted:
        # 主动中断：返回空解集，错误消息统一为"优化已被用户中断"。
        # OptimizationAborted 仅在标记置位时抛出（入口检查或每代检查），
        # 发送事件前标记必然仍置位，直接以失败结果走回调通道。
        callback.on_complete(
            OptimizationResult(
                session_id=session_id,
                status="failed",
                solutions=[],
                error_message="优化已被用户中断",
            )
        )
        return session_id

    # 检查是否找到可行解
    if res.X is None or len(res.X) == 0:
        result = OptimizationResult(
            session_id=session_id,
            status="failed",
            solutions=[],
            error_message="未找到满足资源约束的可行解，请放宽资源限制后重试",
        )
        callback.on_complete(result)
        return session_id

    # 解码结果
    resource_constraint_ids = list(request.resource_constraints.keys())

    # 去重（pymoo NSGA2 仅按 X 相等去重，许多不同 X 可能映射到同一目标三元组）
    if TYPE_CHECKING:
        assert res.F is not None  # res.F is not None when res.X is not None
    final_idx = _dedup_pareto_indices(res.F, res.X)

    solutions: List[SolutionOutput] = []
    for new_id, i in enumerate(final_idx):
        xi = res.X[i].astype(int)
        modes = xi[: problem.n_tasks]
        offsets = xi[problem.n_tasks :]

        # 计算最早开始时间
        T_G = get_adjusted_durations_vectorized(
            problem.base_durations, modes, request.accelerated_ratio
        )
        total_time, earliest_starts = compute_total_time(
            T_G.tolist(),
            offsets.tolist(),
            problem.in_degree,
            problem.graph,
            problem.task_ids,
            problem.task_id_to_idx,
        )

        earliest_starts_array = np.array(
            [earliest_starts[tid] for tid in problem.task_ids], dtype=np.float64
        )

        # 资源约束违反
        violations = calculate_resource_violations_vectorized(
            T_G,
            earliest_starts_array,
            problem.base_resource_usage_matrix,
            problem.resource_constraints,
        )
        violation_dict = {
            resource_constraint_ids[j]: float(max(0, violations[j]))
            for j in range(len(resource_constraint_ids))
        }

        # peak_personnel 与 housing
        peak_personnel = problem._compute_peak_personnel(T_G, earliest_starts_array)
        housing_rooms = problem._compute_housing_rooms(peak_personnel)

        solutions.append(
            SolutionOutput(
                solution_id=new_id,
                modes=modes.tolist(),
                offsets=offsets.tolist(),
                starts=[earliest_starts[tid] for tid in problem.task_ids],
                cost=float(res.F[i, 0]),
                emission=float(res.F[i, 1]),
                duration=float(res.F[i, 2]),
                violations=violation_dict,
                peak_personnel=peak_personnel,
                housing_rooms=housing_rooms,
            )
        )

    # 返回结果
    result = OptimizationResult(
        session_id=session_id,
        status="completed",
        solutions=solutions,
    )
    callback.on_complete(result)

    return session_id
