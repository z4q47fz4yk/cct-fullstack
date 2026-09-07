/**
 * 数据体检 API 封装
 *
 * 拉取项目内有使用记录的资源诊断列表（服务端打标志，前端仅渲染）。
 * 只读、非侵入：不阻断任何流程。
 */
import { computed } from 'vue'
import { useQuery, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import {
  resourceDiagnosticsQuery,
  resourceDiagnosticsQueryKey,
  tagChartDiagnosticsQuery,
  tagChartDiagnosticsQueryKey,
} from '@/client/@pinia/colada.gen'
import type { ResourceDiagnosticsResp } from '@/client/types.gen'

/** 用量口径 */
export type DiagnosticsUsageType = 'ALL' | 'ACTUAL' | 'PLANNED'

export function useDiagnosticsApi(usageType: () => DiagnosticsUsageType) {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const query = useQuery(() => ({
    ...resourceDiagnosticsQuery({
      path: { project_id: currentProjectId.value! },
      query: { usage_type: usageType() },
    }),
    enabled: !!currentProjectId.value,
    staleTime: 30_000,
  }))

  const data = computed<ResourceDiagnosticsResp | null>(() => query.state.value?.data ?? null)
  const items = computed(() => data.value?.items ?? [])
  const isLoading = computed(() => query.asyncStatus.value === 'loading')

  /** ZERO_FACTOR 条数（warning 级，供入口徽标使用） */
  const zeroFactorCount = computed(
    () => items.value.filter((it) => it.flags?.includes('ZERO_FACTOR')).length,
  )
  /** info 级条数（仅有 NEGATIVE_FACTOR / ZERO_PRICE 的资源） */
  const infoCount = computed(
    () =>
      items.value.filter((it) => {
        const flags = it.flags ?? []
        return flags.length > 0 && !flags.includes('ZERO_FACTOR')
      }).length,
  )

  async function refresh() {
    await queryCache.invalidateQueries({
      key: resourceDiagnosticsQueryKey({
        path: { project_id: currentProjectId.value! },
        query: { usage_type: usageType() },
      }),
    })
  }

  return { data, items, isLoading, zeroFactorCount, infoCount, refresh, error: query.error }
}

/**
 * 标签/切片配置体检（同一图表内不同切片标签重叠 → 饼图重复计入）。
 * 只读提示，可「重新检查」刷新。
 */
export function useTagChartDiagnostics() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const query = useQuery(() => ({
    ...tagChartDiagnosticsQuery({
      path: { project_id: currentProjectId.value! },
    }),
    enabled: !!currentProjectId.value,
  }))

  const items = computed(() => query.state.value?.data?.items ?? [])
  const isLoading = computed(() => query.asyncStatus.value === 'loading')

  async function refresh() {
    await queryCache.invalidateQueries({
      key: tagChartDiagnosticsQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  }

  return { items, isLoading, refresh, error: query.error }
}
