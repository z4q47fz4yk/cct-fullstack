import { computed } from 'vue'
import { useProjectStorage } from '@/composables/useProjectStorage'
import type { UsageType } from '@/client/types.gen'

/**
 * 资源使用录入的 usageType 切换
 *
 * - batch 级共享 ACTUAL/PLANNED
 * - 按项目持久化（useProjectStorage）
 * - usageType 直接暴露 stored（可写 Ref），配合 v-model 使用
 */
export function useUsageTypeToggle() {
  const stored = useProjectStorage<UsageType>('resource-usage:usage-type', 'ACTUAL')

  const isPlanned = computed({
    get: () => stored.value === 'PLANNED',
    set: (v: boolean) => {
      stored.value = v ? 'PLANNED' : 'ACTUAL'
    },
  })

  const togglePlanned = () => {
    isPlanned.value = !isPlanned.value
  }

  return { isPlanned, togglePlanned, usageType: stored }
}
