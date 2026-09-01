import { computed } from 'vue'
import type { Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import type {
  ResourceUsageBatchCreate,
  ResourceUsageBatchItem,
  ResourceUsageBatchResp,
  ResourceUsageResp,
  ResourceUsageUpdate,
  ResourceUsageWithTagsResp,
  UsageType,
} from '@/client/types.gen'
import {
  listResourceUsagesQuery,
  listResourceUsagesQueryKey,
  batchCreateResourceUsageMutation,
  updateResourceUsageMutation,
  deleteResourceUsageMutation,
} from '@/client/@pinia/colada.gen'

/** 历史 tab 用量类型筛选值；'ALL' / null = 后端"返回全部"语义 */
export type ResourceUsageFilterUsageType = UsageType | 'ALL' | null

/** 资源使用量筛选条件 */
export interface ResourceUsageFilters {
  dateFrom?: string | null
  dateTo?: string | null
  taskIds?: number[] | null
  resourceIds?: number[] | null
  batchId?: string | null
  usageType?: ResourceUsageFilterUsageType
}

export interface UseResourceUsageApiOptions {
  filters: Ref<ResourceUsageFilters>
  page: Ref<number>
  pageSize: Ref<number>
}

/**
 * 资源使用量 API 封装
 * - 后端只提供 batch 创建端点（手动录入），单条创建已删除
 * - 提供列表、批量创建、更新、删除操作
 */
export function useResourceUsageApi(options: UseResourceUsageApiOptions) {
  const { filters, page, pageSize } = options
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  /**
   * 缓存失效函数
   * 让所有 filter 组合的列表缓存都刷新
   */
  const invalidateUsagesCache = async () => {
    await queryCache.invalidateQueries({
      key: listResourceUsagesQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  }

  // 查询资源使用量列表（include_tags 附带直接挂载的标签，供批次列表标签展示）
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listResourceUsagesQuery({
      path: { project_id: currentProjectId.value! },
      query: {
        date: filters.value.dateFrom || null,
        task_ids: filters.value.taskIds ?? null,
        resource_ids: filters.value.resourceIds ?? null,
        batch_id: filters.value.batchId || null,
        // 'ALL' / null / undefined 都映射为 null → 后端"返回全部"
        usageType:
          filters.value.usageType === 'ALL' || filters.value.usageType == null
            ? null
            : filters.value.usageType,
        include_tags: true,
        page: page.value,
        per_page: pageSize.value,
      },
    }),
  )

  const usages = computed<ResourceUsageWithTagsResp[]>(() => state.value?.data?.items ?? [])
  const totalCount = computed(() => state.value?.data?.total ?? 0)
  const isLoading = computed(() => asyncStatus.value === 'loading')

  // 批量创建（手动录入的唯一创建路径）
  const { mutateAsync: createUsageBatch, asyncStatus: createBatchStatus } = useMutation({
    ...batchCreateResourceUsageMutation(),
    onSuccess: invalidateUsagesCache,
  })

  // 更新
  const { mutateAsync: updateUsage, asyncStatus: updateStatus } = useMutation({
    ...updateResourceUsageMutation(),
    onSuccess: invalidateUsagesCache,
  })

  // 删除
  const { mutateAsync: deleteUsage, asyncStatus: deleteStatus } = useMutation({
    ...deleteResourceUsageMutation(),
    onSuccess: invalidateUsagesCache,
  })

  /**
   * 一次性删除某个 batch 的所有记录
   * （后端无批量删除端点，逐条删除）
   */
  async function deleteBatch(
    items: ResourceUsageResp[],
  ): Promise<{ deleted: number; failed: number }> {
    let deleted = 0
    let failed = 0
    for (const u of items) {
      try {
        await deleteUsage({ path: { project_id: currentProjectId.value!, id: u.id } })
        deleted += 1
      } catch (e) {
        failed += 1
        console.error('Failed to delete usage', u.id, e)
      }
    }
    return { deleted, failed }
  }

  const isSubmitting = computed(
    () =>
      createBatchStatus.value === 'loading' ||
      updateStatus.value === 'loading' ||
      deleteStatus.value === 'loading',
  )

  return {
    // 查询相关
    usages,
    totalCount,
    isLoading,
    error,
    refresh,
    // Mutation 相关
    createUsageBatch,
    updateUsage,
    deleteUsage,
    deleteBatch,
    isSubmitting,
    // 缓存管理
    invalidateUsagesCache,
  }
}

/**
 * 按日期（可选按类型）拉取全部使用量记录（无分页），用于前端预检「同日重复」
 * query key 与普通列表查询独立，避免污染筛选页面缓存
 *
 * 传 usageType 时仅预检该口径的记录：
 * 唯一约束含 usage_type，同一 (task, resource, date) 的 ACTUAL 与 PLANNED
 * 本可共存，若不过滤会把不同口径误判为冲突。
 */
export function useResourceUsagesByDate(
  date: Ref<string | null>,
  usageType?: Ref<UsageType | null>,
) {
  const { currentProjectId } = useProjectContext()
  const { state, refresh } = useQuery(() => {
    const pid = currentProjectId.value
    const d = date.value
    const t = usageType?.value ?? null
    return {
      ...listResourceUsagesQuery({
        path: { project_id: pid! },
        query: {
          date: d || null,
          usageType: t || undefined,
          include_tags: true,
          page: 1,
          per_page: FETCH_ALL_PAGE_SIZE,
        },
      }),
      // 日期 / 项目为空时禁用
      enabled: !!d && pid !== null,
    }
  })
  const records = computed<ResourceUsageWithTagsResp[]>(() => state.value?.data?.items ?? [])
  return { records, refresh }
}

/** 兼容旧引用 */
export { listResourceUsagesQueryKey }
export type {
  ResourceUsageBatchCreate,
  ResourceUsageBatchItem,
  ResourceUsageBatchResp,
  ResourceUsageResp,
  ResourceUsageUpdate,
  ResourceUsageWithTagsResp,
}
