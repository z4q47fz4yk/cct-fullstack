/**
 * 优化参数（RunConfig）前端字段级校验规则
 *
 * 与后端 schema 约束对齐（openapi.json /components/schemas/RunConfig）：
 * - popSize / maxGen：正整数（NSGA-II 种群至少 4 个个体）
 * - irr：0 ~ 10；acceleratedRatio：0.1 ~ 1；maxOffset：非负整数
 *
 * 在「开始优化」提交前做字段级校验，避免非法参数直发后端、
 * 仅弹「启动优化失败」而无字段级提示。
 */
import type { RunConfig } from '@/client/types.gen'

export type RunConfigKey = 'popSize' | 'maxGen' | 'irr' | 'acceleratedRatio' | 'maxOffset'

export interface RunConfigRule {
  /** 允许最小值（含） */
  min: number
  /** 允许最大值（含） */
  max: number
  /** 输入步进 */
  step: number
  /** 是否必须为整数 */
  integer?: boolean
  /** 校验失败（含未填写）提示文案 */
  message: string
}

export const RUN_CONFIG_RULES: Record<RunConfigKey, RunConfigRule> = {
  popSize: {
    min: 4,
    max: 10000,
    step: 1,
    integer: true,
    message: '种群大小需为 4 ~ 10000 的整数（NSGA-II 至少 4 个个体）',
  },
  maxGen: {
    min: 1,
    max: 10000,
    step: 1,
    integer: true,
    message: '最大代数需为 1 ~ 10000 的整数',
  },
  irr: {
    min: 0,
    max: 10,
    step: 0.01,
    message: '名义年利率需在 0 ~ 10 之间',
  },
  acceleratedRatio: {
    min: 0.1,
    max: 1,
    step: 0.01,
    message: '加速工期比例需在 0.1 ~ 1 之间',
  },
  maxOffset: {
    min: 0,
    max: 365,
    step: 1,
    integer: true,
    message: '最大偏移天数需为 0 ~ 365 的整数',
  },
}

/** 单字段校验：返回错误文案，null 表示通过 */
export function validateRunConfigField(
  key: RunConfigKey,
  value: number | null | undefined,
): string | null {
  const rule = RUN_CONFIG_RULES[key]
  if (value === null || value === undefined || Number.isNaN(value)) return rule.message
  if (!Number.isFinite(value)) return rule.message
  if (rule.integer && !Number.isInteger(value)) return rule.message
  if (value < rule.min || value > rule.max) return rule.message
  return null
}

/** 整份配置校验：返回 字段 → 错误文案 的映射（空对象 = 全部通过） */
export function validateRunConfig(config: RunConfig): Partial<Record<RunConfigKey, string>> {
  const errors: Partial<Record<RunConfigKey, string>> = {}
  for (const key of Object.keys(RUN_CONFIG_RULES) as RunConfigKey[]) {
    const message = validateRunConfigField(key, config[key])
    if (message) errors[key] = message
  }
  return errors
}
