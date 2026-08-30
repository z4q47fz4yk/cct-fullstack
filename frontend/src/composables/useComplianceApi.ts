/**
 * 计划践行度 API 封装
 *
 * 一次返回全部对照数据（工期/成本/碳排/工序完成时间/材料差异/每月对照）；
 * 无 PLANNED 基线返回 409；评价解锁以 evaluationUnlocked 为准。
 */
import { computed } from 'vue'
import { useQuery } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import { complianceQuery } from '@/client/@pinia/colada.gen'

export function useComplianceApi() {
  const { currentProjectId } = useProjectContext()

  const query = useQuery(() => ({
    ...complianceQuery({ path: { project_id: currentProjectId.value! } }),
    enabled: !!currentProjectId.value,
  }))

  const data = computed(() => query.state.value?.data ?? null)
  const isLoading = computed(() => query.asyncStatus.value === 'loading')

  /** 409 = 尚无 PLANNED 基线 */
  const isNoPlan = computed(() => {
    const e = query.error.value as { status?: number } | null
    return e?.status === 409
  })

  return {
    data,
    isLoading,
    isNoPlan,
    error: query.error,
    refresh: query.refresh,
  }
}
