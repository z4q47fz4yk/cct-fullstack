import { computed } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type { ResourceReuseConfigResp } from '@/types/reuseConfig'
import {
  listReuseConfigsQuery,
  listReuseConfigsQueryKey,
  createReuseConfigMutation,
  updateReuseConfigMutation,
  deleteReuseConfigMutation,
} from '@/client/@pinia/colada.gen'

/**
 * 可周转材料复用配置 API 封装
 * 提供复用配置的 CRUD 操作和缓存管理
 */
export function useReuseConfigApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  /**
   * 缓存失效函数
   * 用于在创建、更新、删除操作后刷新列表缓存
   */
  const invalidateConfigsCache = async () => {
    await queryCache.invalidateQueries({
      key: listReuseConfigsQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  }

  // 查询复用配置列表
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listReuseConfigsQuery({
      path: { project_id: currentProjectId.value! },
    }),
  )

  const configs = computed<ResourceReuseConfigResp[]>(() => state.value?.data?.items ?? [])
  const totalConfigs = computed(() => state.value?.data?.total ?? 0)
  const isLoading = computed(() => asyncStatus.value === 'loading')

  // 创建复用配置
  const { mutateAsync: createConfig, asyncStatus: createStatus } = useMutation({
    ...createReuseConfigMutation(),
    onSuccess: invalidateConfigsCache,
  })

  // 更新复用配置
  const { mutateAsync: updateConfig, asyncStatus: updateStatus } = useMutation({
    ...updateReuseConfigMutation(),
    onSuccess: invalidateConfigsCache,
  })

  // 删除复用配置
  const { mutateAsync: deleteConfig, asyncStatus: deleteStatus } = useMutation({
    ...deleteReuseConfigMutation(),
    onSuccess: invalidateConfigsCache,
  })

  const isSubmitting = computed(
    () =>
      createStatus.value === 'loading' ||
      updateStatus.value === 'loading' ||
      deleteStatus.value === 'loading',
  )

  return {
    // 查询相关
    configs,
    totalConfigs,
    isLoading,
    error,
    refresh,
    // Mutation 相关
    createConfig,
    updateConfig,
    deleteConfig,
    isSubmitting,
    // 缓存管理
    invalidateConfigsCache,
  }
}

// 导出查询 Key 函数，供外部使用
export { listReuseConfigsQueryKey }
