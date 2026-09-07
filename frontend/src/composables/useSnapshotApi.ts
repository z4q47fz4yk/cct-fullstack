/**
 * usage_snapshot 物化视图 API 封装
 *
 * 提供：刷新信息查询（上次/下次刷新时间）、手动强制刷新、合并标签用量列表。
 */
import { computed } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import {
  listUsageSnapshotQuery,
  usageSnapshotManualRefreshMutation,
  usageSnapshotRefreshInfoQuery,
  usageSnapshotRefreshInfoQueryKey,
} from '@/client/@pinia/colada.gen'

export function useSnapshotRefreshInfo() {
  const { currentProjectId } = useProjectContext()
  const query = useQuery(() => ({
    ...usageSnapshotRefreshInfoQuery({
      path: { project_id: currentProjectId.value! },
    }),
    enabled: !!currentProjectId.value,
  }))

  const info = computed(() => query.state.value?.data ?? null)
  const isLoading = computed(() => query.asyncStatus.value === 'loading')

  return { info, isLoading, refresh: query.refresh, error: query.error }
}

export function useSnapshotManualRefresh() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const { mutateAsync: refreshSnapshot, asyncStatus } = useMutation({
    ...usageSnapshotManualRefreshMutation(),
    onSuccess: async () => {
      await queryCache.invalidateQueries({
        key: usageSnapshotRefreshInfoQueryKey({
          path: { project_id: currentProjectId.value! },
        }),
      })
    },
  })

  const isRefreshing = computed(() => asyncStatus.value === 'loading')

  return { refreshSnapshot, isRefreshing }
}

/** 合并标签用量列表（列表项含 tags[] 合并结果） */
export function useSnapshotUsages() {
  const { currentProjectId } = useProjectContext()
  const query = useQuery(() => ({
    ...listUsageSnapshotQuery({
      path: { project_id: currentProjectId.value! },
      query: { per_page: 1000 },
    }),
    enabled: !!currentProjectId.value,
  }))

  const items = computed(() => query.state.value?.data?.items ?? [])
  return { items, isLoading: computed(() => query.asyncStatus.value === 'loading') }
}
