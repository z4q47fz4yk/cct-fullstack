import { computed } from 'vue'
import type { Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
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
  /** 批次筛选原文：手动批次完整数字 ID / 日报批次 UUID / 其它（前端模糊匹配） */
  batchId?: string | null
  usageType?: ResourceUsageFilterUsageType
}

/** 批次筛选输入分类：纯数字 = 手动批次 ID；UUID = 日报批次 UUID；其它 = 前端模糊匹配 */
type BatchFilterKind = 'none' | 'manual' | 'uuid' | 'fuzzy'

const UUID_RE = /^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$/

/** 手动批次 ID 解析：纯数字且在安全整数范围内才返回 number */
function parseManualBatchId(raw: string): number | null {
  if (!/^\d+$/.test(raw)) return null
  const n = Number(raw)
  return Number.isSafeInteger(n) ? n : null
}

function classifyBatchFilter(raw: string): BatchFilterKind {
  if (!raw) return 'none'
  if (parseManualBatchId(raw) !== null) return 'manual'
  if (UUID_RE.test(raw)) return 'uuid'
  return 'fuzzy'
}

export interface UseResourceUsageApiOptions {
  filters: Ref<ResourceUsageFilters>
}

/**
 * 提取记录所属批次 id：手动 batch 取 manualBatchId，日报 batch 取 batchId。
 * 二者在业务上互斥；无批次返回 null。
 */
export function getUsageBatchId(u: {
  batchId?: string | null
  manualBatchId?: number | null
}): string | number | null {
  if (u.manualBatchId != null) return u.manualBatchId
  if (u.batchId != null) return u.batchId
  return null
}

/**
 * (usage-date, batch-id) 复合分块键。
 * 同一 batch 若含多天记录会被拆成多个分块；无批次记录返回 null。
 */
export function getUsageChunkKey(u: {
  usageDate?: string | null
  batchId?: string | null
  manualBatchId?: number | null
}): string | null {
  const rawId = getUsageBatchId(u)
  if (rawId === null) return null
  const date = u.usageDate?.slice(0, 10) ?? ''
  if (!date) return null
  return `${date}|${rawId}`
}

/**
 * 资源使用量 API 封装
 * - 后端只提供 batch 创建端点（手动录入），单条创建已删除
 * - 提供列表、批量创建、更新、删除操作
 */
export function useResourceUsageApi(options: UseResourceUsageApiOptions) {
  const { filters } = options
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

  // 批次筛选输入分类（E-2）：
  // - 完整数字 ID → 后端 manual_batch_id 精确过滤（手动批次）
  // - UUID → 后端 batch_id 精确过滤（日报批次）
  // - 其它（部分 ID / 非法输入）→ 后端无模糊参数（batch_id 传非 UUID 会 422），
  //   不带批次参数取回窗口数据后由前端按批次 id 包含匹配
  const rawBatchFilter = computed(() => (filters.value.batchId ?? '').trim())
  const batchFilterKind = computed<BatchFilterKind>(() => classifyBatchFilter(rawBatchFilter.value))

  // 查询资源使用量列表（include_tags 附带直接挂载的标签，供批次列表标签展示）
  // 后端该端点不分页：按筛选条件返回窗口内全部记录，前端再按 (usage-date, batch-id) 分块
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listResourceUsagesQuery({
      path: { project_id: currentProjectId.value! },
      query: {
        from_date: filters.value.dateFrom || null,
        to_date: filters.value.dateTo || null,
        task_ids: filters.value.taskIds ?? null,
        resource_ids: filters.value.resourceIds ?? null,
        batch_id: batchFilterKind.value === 'uuid' ? rawBatchFilter.value : null,
        manual_batch_id:
          batchFilterKind.value === 'manual' ? parseManualBatchId(rawBatchFilter.value) : null,
        // 'ALL' / null / undefined 都映射为 null → 后端"返回全部"
        usageType:
          filters.value.usageType === 'ALL' || filters.value.usageType == null
            ? null
            : filters.value.usageType,
        include_tags: true,
      },
    }),
  )

  const usages = computed<ResourceUsageWithTagsResp[]>(() => {
    const items = state.value?.data?.items ?? []
    if (batchFilterKind.value !== 'fuzzy') return items
    // 前端模糊匹配：批次 id / UUID 均以字符串包含匹配
    const raw = rawBatchFilter.value.toLowerCase()
    return items.filter((u) => {
      const id = getUsageBatchId(u)
      return id !== null && String(id).toLowerCase().includes(raw)
    })
  })
  const totalCount = computed(() =>
    batchFilterKind.value === 'fuzzy' ? usages.value.length : (state.value?.data?.total ?? 0),
  )
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
          // 精确日查询 = 起止同为该日期
          from_date: d || null,
          to_date: d || null,
          usageType: t || undefined,
          include_tags: true,
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
