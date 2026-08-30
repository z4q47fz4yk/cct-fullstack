import { computed } from 'vue'
import type { Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type { ResourceCategory, ResourceCategoryStat } from '@/client/types.gen'
import {
  listResourcesQuery,
  listResourcesQueryKey,
  createResourceMutation,
  updateResourceMutation,
  deleteResourceMutation,
  getResourceStatsByCategoryQuery,
} from '@/client/@pinia/colada.gen'

export interface UseResourceApiOptions {
  category: Ref<ResourceCategory>
  searchQuery: Ref<string>
  page: Ref<number>
  pageSize: Ref<number>
}

/**
 * 资源管理 API 封装
 * 分离 API 调用逻辑与 UI 逻辑
 */
export function useResourceApi(options: UseResourceApiOptions) {
  const { category, searchQuery } = options
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  // 统一的缓存刷新函数
  const invalidateResourcesCache = async () => {
    await queryCache.invalidateQueries({
      key: listResourcesQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  }

  // 查询资源列表（include_tags 附带直接挂载的标签，供表格标签列展示）
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listResourcesQuery({
      path: { project_id: currentProjectId.value! },
      query: {
        category: category.value,
        name: searchQuery.value?.trim() || null,
        page: options.page.value,
        per_page: options.pageSize.value,
        include_tags: true,
      },
    }),
  )

  const apiResources = computed(() => state.value?.data?.items ?? [])
  const totalCount = computed(() => state.value?.data?.total ?? 0)
  const isLoading = computed(() => asyncStatus.value === 'loading')

  // 创建资源
  const { mutateAsync: createResource, asyncStatus: createStatus } = useMutation({
    ...createResourceMutation(),
    onSuccess: invalidateResourcesCache,
  })

  // 更新资源
  const { mutateAsync: updateResource, asyncStatus: updateStatus } = useMutation({
    ...updateResourceMutation(),
    onSuccess: invalidateResourcesCache,
  })

  // 删除资源
  const { mutateAsync: deleteResource } = useMutation({
    ...deleteResourceMutation(),
    onSuccess: invalidateResourcesCache,
  })

  const isSubmitting = computed(
    () => createStatus.value === 'loading' || updateStatus.value === 'loading',
  )

  // 获取分类统计
  const { data: statsState, asyncStatus: statsAsyncStatus } = useQuery(() =>
    getResourceStatsByCategoryQuery({
      path: { project_id: currentProjectId.value! },
    }),
  )

  const categoryStats = computed<ResourceCategoryStat[]>(() => {
    return statsState.value || []
  })
  const isStatsLoading = computed(() => statsAsyncStatus.value === 'loading')

  return {
    // 查询相关
    apiResources,
    totalCount,
    isLoading,
    error,
    refresh,
    // 分类统计
    categoryStats,
    isStatsLoading,
    // Mutation 相关
    createResource,
    updateResource,
    deleteResource,
    isSubmitting,
  }
}
