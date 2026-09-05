import { computed } from 'vue'
import { useQuery } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import { getResourceUsageCarbonStatsQuery } from '@/client/@pinia/colada.gen'
import type { CarbonUsageStat, ResourceCategory } from '@/client/types.gen'

export interface CategoryEmission {
  category: ResourceCategory
  emissionKg: number
}

export interface MonthEmission {
  month: string
  emissionKg: number
}

/** 单资源总排放（用于 Top N 排行） */
export interface ResourceEmission {
  resourceId: number
  resourceName: string
  category: ResourceCategory
  emissionKg: number
}

/** 按月 × 资源类别的交叉聚合（用于堆叠柱状图） */
export interface MonthCategoryEmission {
  month: string
  monthIndex: number
  byCategory: Record<ResourceCategory, number>
}

/**
 * 报表条目（月粒度视图投影）。
 *
 * 后端新聚合端点返回 period/periodIndex（随颗粒度 day/week/month 自描述）；
 * 既有页面全部按「月」消费，故在 composable 层把 period 投影为 month、
 * periodIndex 投影为 monthIndex，其余字段（resourceId/name/category/
 * quantity/cost/emission/bucket）原样保留。
 */
export interface CarbonMonthItem extends CarbonUsageStat {
  /** 周期首日（月粒度 = 月初）ISO 日期串 */
  month: string
  /** 从首期起的序号（1-based） */
  monthIndex: number
}

/**
 * 碳排放统计 composable
 *
 * 数据源：GET /projects/{project_id}/resource-usage/stats/carbon
 * 服务端按 (资源 × 粒度) SQL 聚合（只读 usage 表，ACTUAL/PLANNED 独立），
 * 客户端仅做二次分组（类别 / 按月 / 资源 / 交叉）。当前消费方均为月粒度，
 * 由本层做 period → month 投影，页面零改动。
 *
 * 404 检测：接口返回 404 时 isNotFound 为 true（页面层负责跳转）
 */
export function useCarbonStats() {
  const { currentProjectId } = useProjectContext()

  const { state, asyncStatus, error, refresh } = useQuery(() =>
    getResourceUsageCarbonStatsQuery({
      path: { project_id: currentProjectId.value! },
      query: { usageType: 'ACTUAL', granularity: 'month' },
    }),
  )

  const resp = computed(() => state.value?.data)

  // ─── 原始数据（period → month 投影，兼容既有月粒度视图） ───
  const items = computed<CarbonMonthItem[]>(() =>
    (resp.value?.items ?? []).map((x) => ({
      ...x,
      month: x.period,
      monthIndex: x.periodIndex,
    })),
  )

  // ─── 总量 ────────────────────────────────────────────────
  const totalEmissionKg = computed(() => {
    let sum = 0
    for (const x of items.value) sum += x.emission
    return sum
  })

  const totalEmissionTon = computed(() => totalEmissionKg.value / 1000)

  // 总成本（名义，用量 × 有效单价，含周转折减）
  const totalCost = computed(() => {
    let sum = 0
    for (const x of items.value) sum += x.cost ?? 0
    return sum
  })

  // ─── 元信息（来自响应顶层；月粒度下即覆盖月份数） ─────────
  const totalMonths = computed(() => resp.value?.totalPeriods ?? 0)
  const totalResources = computed(() => resp.value?.totalResources ?? 0)

  // ─── 按资源类别聚合 ──────────────────────────────────────
  const byCategory = computed<CategoryEmission[]>(() => {
    const m = new Map<ResourceCategory, number>()
    for (const x of items.value) {
      m.set(x.category, (m.get(x.category) ?? 0) + x.emission)
    }
    return Array.from(m.entries())
      .map(([category, emissionKg]) => ({ category, emissionKg }))
      .sort((a, b) => b.emissionKg - a.emissionKg)
  })

  // ─── 按月聚合 ────────────────────────────────────────────
  const byMonth = computed<MonthEmission[]>(() => {
    const m = new Map<string, number>()
    for (const x of items.value) {
      m.set(x.month, (m.get(x.month) ?? 0) + x.emission)
    }
    return Array.from(m.entries())
      .map(([month, emissionKg]) => ({ month, emissionKg }))
      .sort((a, b) => a.month.localeCompare(b.month))
  })

  // ─── 按月 × 资源类别交叉聚合 ────────────────────────────
  const byMonthCategory = computed<MonthCategoryEmission[]>(() => {
    // 月份索引与每类排放
    const monthMap = new Map<
      string,
      { monthIndex: number; byCategory: Record<ResourceCategory, number> }
    >()
    for (const x of items.value) {
      if (!monthMap.has(x.month)) {
        monthMap.set(x.month, {
          monthIndex: x.monthIndex,
          byCategory: { labor: 0, machinery: 0, material: 0, transport: 0, others: 0 },
        })
      }
      const entry = monthMap.get(x.month)!
      entry.byCategory[x.category] += x.emission
    }
    return Array.from(monthMap.entries())
      .map(([month, v]) => ({ month, ...v }))
      .sort((a, b) => a.month.localeCompare(b.month))
  })

  // ─── 按资源聚合（用于 Top N） ────────────────────────────
  const byResource = computed<ResourceEmission[]>(() => {
    const m = new Map<number, { name: string; category: ResourceCategory; total: number }>()
    for (const x of items.value) {
      const cur = m.get(x.resourceId)
      if (cur) cur.total += x.emission
      else m.set(x.resourceId, { name: x.resourceName, category: x.category, total: x.emission })
    }
    return Array.from(m.entries())
      .map(([resourceId, v]) => ({
        resourceId,
        resourceName: v.name,
        category: v.category,
        emissionKg: v.total,
      }))
      .sort((a, b) => b.emissionKg - a.emissionKg)
  })

  // ─── 按水电桶 / 类别聚合（bucket 优先，评价“水电（新）”桶） ──
  const byBucket = computed<{ bucket: string; emissionKg: number; cost: number }[]>(() => {
    const m = new Map<string, { emissionKg: number; cost: number }>()
    for (const x of items.value) {
      const bucket = x.bucket ?? x.category
      const cur = m.get(bucket)
      if (cur) {
        cur.emissionKg += x.emission
        cur.cost += x.cost ?? 0
      } else {
        m.set(bucket, { emissionKg: x.emission, cost: x.cost ?? 0 })
      }
    }
    return Array.from(m.entries())
      .map(([bucket, v]) => ({ bucket, ...v }))
      .sort((a, b) => b.emissionKg - a.emissionKg)
  })

  // ─── 按月成本聚合（名义月成本） ──────────────────────────
  const byMonthCost = computed<{ month: string; cost: number }[]>(() => {
    const m = new Map<string, number>()
    for (const x of items.value) {
      m.set(x.month, (m.get(x.month) ?? 0) + (x.cost ?? 0))
    }
    return Array.from(m.entries())
      .map(([month, cost]) => ({ month, cost }))
      .sort((a, b) => a.month.localeCompare(b.month))
  })

  // ─── 状态 ────────────────────────────────────────────────
  const isLoading = computed(() => asyncStatus.value === 'loading')

  // 404 表示项目不存在；页面层（如 EmissionAnalysisTab）watch 此值并跳转到 404 路由
  const isNotFound = computed(() => {
    const e = error.value as { status?: number; response?: { status?: number } } | null
    return e?.status === 404 || e?.response?.status === 404
  })

  return {
    // 原始数据
    items,
    // 总量
    totalEmissionKg,
    totalEmissionTon,
    totalCost,
    totalMonths,
    totalResources,
    // 聚合
    byCategory,
    byMonth,
    byMonthCategory,
    byResource,
    byBucket,
    byMonthCost,
    // 状态
    isLoading,
    isNotFound,
    error,
    refresh,
  }
}
