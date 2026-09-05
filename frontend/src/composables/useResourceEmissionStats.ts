import { computed } from 'vue'
import { useQuery } from '@pinia/colada'
import { getResourceUsageCarbonStatsQuery } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'
import type { CarbonUsageStat, ResourceCategory } from '@/client/types.gen'

/**
 * 单个资源在某维度（实际 / 计划）下的总排放（单位 kgCO₂e）
 */
export interface ResourceEmissionSplit {
  resourceId: number
  resourceName: string
  category: ResourceCategory
  /** 实际总排放（kg） */
  actual: number
  /** 计划总排放（kg） */
  planned: number
}

/**
 * 并行拉取 ACTUAL 和 PLANNED 两个维度的周期碳排，客户端按 (resourceId) 合并
 *
 * 数据源：GET /resource-usage/stats/carbon（usage 表按 usage_type 过滤聚合）。
 * 后端限制：单次请求只能按一种 usageType 过滤，故 ACTUAL/PLANNED 各请求一次。
 * 两个维度语义均为「用量表口径」：实际 = usage_type=ACTUAL，计划 = usage_type=PLANNED，
 * 不读取计划基线（baseline）快照。
 *
 * 与 useCarbonStats 的区别：
 * - useCarbonStats 仅取 ACTUAL（月粒度），用于 insights/settings 碳排分析页
 * - 本 composable 同时取 ACTUAL + PLANNED，专供「分组对比」视图
 *
 * 缓存隔离：`@pinia/colada` 按 query 入参生成 cache key，
 * ACTUAL 和 PLANNED 是两个独立缓存条目。
 */
export function useResourceEmissionStats() {
  const { currentProjectId } = useProjectContext()

  // 实际用量
  const actualQuery = useQuery(() =>
    getResourceUsageCarbonStatsQuery({
      path: { project_id: currentProjectId.value! },
      query: { usageType: 'ACTUAL', granularity: 'month' },
    }),
  )

  // 计划用量
  const plannedQuery = useQuery(() =>
    getResourceUsageCarbonStatsQuery({
      path: { project_id: currentProjectId.value! },
      query: { usageType: 'PLANNED', granularity: 'month' },
    }),
  )

  // ─── 原始数据（忽略周期，仅按资源合并） ─────────────────
  const actualItems = computed<CarbonUsageStat[]>(() => actualQuery.state.value?.data?.items ?? [])
  const plannedItems = computed<CarbonUsageStat[]>(
    () => plannedQuery.state.value?.data?.items ?? [],
  )

  // ─── 按资源合并（不区分周期）────────────────────────────
  const byResource = computed<ResourceEmissionSplit[]>(() => {
    const m = new Map<
      number,
      { name: string; category: ResourceCategory; actual: number; planned: number }
    >()
    const ensure = (id: number, name: string, category: ResourceCategory) => {
      let entry = m.get(id)
      if (!entry) {
        entry = { name, category, actual: 0, planned: 0 }
        m.set(id, entry)
      }
      return entry
    }
    for (const x of actualItems.value) {
      const e = ensure(x.resourceId, x.resourceName, x.category)
      e.actual += x.emission
    }
    for (const x of plannedItems.value) {
      const e = ensure(x.resourceId, x.resourceName, x.category)
      e.planned += x.emission
    }
    return Array.from(m.entries())
      .map(([resourceId, v]) => ({
        resourceId,
        resourceName: v.name,
        category: v.category,
        actual: v.actual,
        planned: v.planned,
      }))
      .sort((a, b) => b.actual + b.planned - (a.actual + a.planned))
  })

  // ─── 状态 ────────────────────────────────────────────────
  const isLoading = computed(
    () =>
      actualQuery.asyncStatus.value === 'loading' || plannedQuery.asyncStatus.value === 'loading',
  )

  const error = computed(() => actualQuery.error.value ?? plannedQuery.error.value)

  const isNotFound = computed(() => {
    const a = actualQuery.error.value as { status?: number; response?: { status?: number } } | null
    const p = plannedQuery.error.value as { status?: number; response?: { status?: number } } | null
    return (
      a?.status === 404 ||
      a?.response?.status === 404 ||
      p?.status === 404 ||
      p?.response?.status === 404
    )
  })

  async function refresh() {
    await Promise.all([actualQuery.refresh(), plannedQuery.refresh()])
  }

  return {
    byResource,
    isLoading,
    isNotFound,
    error,
    refresh,
  }
}
