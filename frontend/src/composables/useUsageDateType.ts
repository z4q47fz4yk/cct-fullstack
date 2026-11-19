/**
 * 资源使用量共享的「日期 + 用量类型」上下文
 *
 * - usageDate：页面级唯一日期（手动录入与日报导入共用，按项目持久化）
 * - 用量类型推断：按「当前日期 vs 项目实际开工日期」自动判断
 *   - 项目未设置实际开工日期 → 默认「计划」
 *   - usageDate < actual_start_date → 「计划」（开工前）
 *   - 否则 → 「实际」
 * - 强制切换（复选框）：按项目持久化（与 usageDate 同模式），
 *   录入页 / 日报导入页共享同一选择，口径跨页面保持一致（E-5）
 */
import { computed } from 'vue'
import { useProjectApi } from '@/composables/useProjectApi'
import { useProjectStorage } from '@/composables/useProjectStorage'
import { todayIsoLocal } from '@/utils/date'
import type { UsageType } from '@/client/types.gen'

/** ISO 日期字符串直接字典序比较即日期序 */
function compareIsoDate(a: string, b: string): number {
  if (a === b) return 0
  return a < b ? -1 : 1
}

export function useUsageDateType() {
  const { project } = useProjectApi()

  // 页面级唯一日期（手动 + 日报共用）
  const usageDate = useProjectStorage<string>('resource-usage:date', todayIsoLocal())

  // 强制切换：按项目持久化，录入页 / 日报导入页共享（跨页保持口径一致）
  const isForced = useProjectStorage<boolean>('resource-usage:forced-usage-type', false)

  /** 项目实际开工日期（可空） */
  const actualStartDate = computed<string | null>(() => project.value?.actual_start_date ?? null)

  /** 推断基准类型（未强制时生效） */
  const inferredUsageType = computed<UsageType>(() => {
    const ad = actualStartDate.value
    if (!ad) return 'PLANNED'
    return compareIsoDate(usageDate.value, ad) < 0 ? 'PLANNED' : 'ACTUAL'
  })

  /** 生效类型：强制时取相反值 */
  const effectiveUsageType = computed<UsageType>(() => {
    const base = inferredUsageType.value
    if (!isForced.value) return base
    return base === 'ACTUAL' ? 'PLANNED' : 'ACTUAL'
  })

  /**
   * 口径说明文案：始终以「当前生效口径」收尾（M-9）。
   * 强制切换时保留推断依据，但明确告知已切换后的口径，避免与头部口径徽标自相矛盾。
   */
  const inferenceReason = computed<string>(() => {
    const ad = actualStartDate.value
    let basis: string
    if (!ad) {
      basis = '项目未设置实际开工日期，推断为「计划」口径'
    } else if (compareIsoDate(usageDate.value, ad) < 0) {
      basis = `使用日期 ${usageDate.value} 早于实际开工日期 ${ad}，推断为「计划」口径`
    } else {
      basis = `使用日期 ${usageDate.value} 不早于实际开工日期 ${ad}，推断为「实际」口径`
    }
    const effectiveLabel = effectiveUsageType.value === 'ACTUAL' ? '实际' : '计划'
    if (!isForced.value) return `${basis}，当前按「${effectiveLabel}」口径录入`
    return `${basis}；已强制切换为「${effectiveLabel}」口径录入`
  })

  /** 强制切换目标文案（复选框标签） */
  const forceLabel = computed<string>(() => {
    const base = inferredUsageType.value
    return base === 'ACTUAL' ? '强制按计划录入' : '强制按实际录入'
  })

  /** 是否正在按「强制」口径（用于界面标记） */
  const isUsingForced = computed<boolean>(() => isForced.value)

  function forceToggle() {
    isForced.value = !isForced.value
  }

  /** 重置强制开关（清除持久化的强制选择，恢复自动推断） */
  function resetForce() {
    isForced.value = false
  }

  return {
    usageDate,
    actualStartDate,
    inferenceReason,
    inferredUsageType,
    effectiveUsageType,
    forceLabel,
    isForced,
    isUsingForced,
    forceToggle,
    resetForce,
  }
}
