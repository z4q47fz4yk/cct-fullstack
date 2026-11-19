/**
 * 资源用量三阶段归因（设计稿：建材生产 / 建材运输 / 施工建造）
 *
 * - 列表「阶段」列徽标、阶段筛选、新增弹窗阶段选项共用同一套口径
 * - 配色对应设计稿 tag-blue / tag-orange / tag-purple
 */
import type { ResourceCategory } from '@/types/resource'

export type UsageStage = 'production' | 'transport' | 'construction'

export const USAGE_STAGE_LABEL: Record<UsageStage, string> = {
  production: '建材生产',
  transport: '建材运输',
  construction: '施工建造',
}

/** 阶段徽标配色（Tailwind 类，主题变量随深浅色自动适配） */
export const USAGE_STAGE_BADGE_CLS: Record<UsageStage, string> = {
  production: 'bg-primary/15 text-primary',
  transport: 'bg-warning/15 text-warning',
  construction: 'bg-purple/15 text-purple',
}

/** 阶段筛选项（「全部」+ 三阶段） */
export const USAGE_STAGE_FILTER_OPTIONS: ReadonlyArray<{
  value: UsageStage | 'all'
  label: string
}> = [
  { value: 'all', label: '全部' },
  { value: 'production', label: '建材生产' },
  { value: 'transport', label: '建材运输' },
  { value: 'construction', label: '施工建造' },
]

/**
 * 资源 → 阶段：资源名含 生产/运输/建造（施工） 关键字优先；
 * 否则按类别归类（材料 → 建材生产，运输 → 建材运输，其余 → 施工建造）。
 */
export function usageStageOf(name: string, category: ResourceCategory | undefined): UsageStage {
  const n = name
  if (n.includes('生产')) return 'production'
  if (n.includes('运输')) return 'transport'
  if (n.includes('建造') || n.includes('施工')) return 'construction'
  if (category === 'material') return 'production'
  if (category === 'transport') return 'transport'
  return 'construction'
}
