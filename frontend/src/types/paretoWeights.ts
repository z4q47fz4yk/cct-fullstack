/**
 * 帕累托解排序权重
 *
 * 用户可调整三组权重（工期/成本/碳排放），用于对 Pareto 解集进行加权评分排序。
 *
 * 公式：
 *   M_i = α·T_i/ΣT + β·C_i/ΣC + γ·E_i/ΣE
 *   其中 α=duration, β=cost, γ=emission（0~100 整数，不要求和为 1）
 *
 * 边界：
 * - 三个权重都为 0 → 所有解得分相同（rank=1）
 * - 0 是合法值（彻底忽略某指标）
 * - 不要求和为 1（让用户独立调整每个指标的关注度）
 */

/** 权重对象：0~100 整数 */
export interface ParetoWeights {
  /** 工期权重 */
  duration: number
  /** 成本权重 */
  cost: number
  /** 碳排放权重 */
  emission: number
}

/** 默认权重：等权 (33/33/33) */
export const DEFAULT_PARETO_WEIGHTS: ParetoWeights = {
  duration: 33,
  cost: 33,
  emission: 33,
}

/** 单个权重字段的元数据（用于 UI label 生成） */
export const WEIGHT_FIELDS = [
  {
    key: 'duration' as const,
    label: '工期',
  },
  {
    key: 'cost' as const,
    label: '成本',
  },
  {
    key: 'emission' as const,
    label: '碳排放',
  },
] as const

/** 权重预设项（用于 chip 按钮快速切换） */
export interface WeightPreset {
  /** 显示文本 */
  label: string
  /** 权重值 */
  values: ParetoWeights
}

/** 用户自定义命名预设（含 id，用于删除） */
export interface NamedWeightPreset extends WeightPreset {
  /** 唯一标识（crypto.randomUUID） */
  id: string
}
