import { computed, unref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type {
  ResourceCategory,
  ResourceCategoryStat,
  ResourceWithConfigResp,
} from '@/client/types.gen'
import {
  listResourcesQuery,
  listResourcesQueryKey,
  createResourceMutation,
  updateResourceMutation,
  deleteResourceMutation,
  getResourceStatsByCategoryQuery,
} from '@/client/@pinia/colada.gen'

export interface UseResourceApiOptions {
  /** 服务端过滤：分类（null=全部） */
  category?: Ref<ResourceCategory | null>
  /** 服务端过滤：名称关键字（LIKE 包含） */
  name?: Ref<string>
  /** 服务端过滤：仅拥有日用量约束的资源（与 reusable 互斥） */
  constrained?: Ref<boolean>
  /** 服务端过滤：仅拥有周转复用配置的资源 */
  reusable?: Ref<boolean>
  /** 服务端过滤：AND 标签过滤——资源必须挂载所有指定标签 */
  tagIds?: Ref<number[]>
  /** 服务端分页：当前页（1-based） */
  page?: Ref<number>
  /** 服务端分页：每页数量 */
  pageSize?: Ref<number>
  /** 是否让后端填充每个资源的 tags（含分类默认标签）。默认 true。 */
  includeTags?: Ref<boolean>
  /** 是否让后端填充每个资源的 constraint 字段。默认 true。 */
  includeConstraint?: Ref<boolean>
  /** 是否让后端填充每个资源的 reuseConfig 字段。默认 true。 */
  includeReuseConfig?: Ref<boolean>
}

/**
 * 资源管理 API 封装
 *
 * - 全部过滤与分页由后端 `listResources` 承担（category / name / constrained /
 *   reusable / tag_ids / page / per_page）；客户端不再做 filter / slice。
 * - `include_tags` / `include_constraint` / `include_reuse_config` 默认 true，
 *   调用方可通过对应 ref 覆盖。
 * - 资源条目直接附带 `tags` / `constraint` / `reuse_config` 字段，徽标 / 筛选 /
 *   弹窗回填直接读字段，无需在前端自行拼装 Map。
 */
export function useResourceApi(options?: UseResourceApiOptions) {
  const {
    category,
    name,
    constrained,
    reusable,
    tagIds,
    page,
    pageSize,
    includeTags,
    includeConstraint,
    includeReuseConfig,
  } = options ?? {}
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  // 统一的缓存刷新函数（任意过滤条件下命中同一 key 时使用）
  const invalidateResourcesCache = async () => {
    await queryCache.invalidateQueries({
      key: listResourcesQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  }

  // 查询资源列表：把过滤与分页直接透传给后端
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listResourcesQuery({
      path: { project_id: currentProjectId.value! },
      query: {
        category: unref(category) ?? undefined,
        name: unref(name) || undefined,
        constrained: unref(constrained),
        reusable: unref(reusable),
        tag_ids: unref(tagIds),
        page: unref(page),
        per_page: unref(pageSize),
        include_tags: unref(includeTags ?? true),
        include_constraint: unref(includeConstraint ?? true),
        include_reuse_config: unref(includeReuseConfig ?? true),
      },
    }),
  )

  /** 当前页资源（每条已附带 tags / constraint / reuse_config） */
  const pagedResources: ComputedRef<ResourceWithConfigResp[]> = computed(
    () => state.value?.data?.items ?? [],
  )

  /** 当前过滤+分页下的总数（后端 total） */
  const totalCount: ComputedRef<number> = computed(() => state.value?.data?.total ?? 0)

  /** 兼容旧 API 命名：旧代码可能消费 `apiResources`。语义改为"当前页资源"。 */
  const apiResources = pagedResources

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
    pagedResources,
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
