/**
 * 碳排放趋势图表配置 composable
 *
 * 双模式：
 * - 'stacked'：按月堆叠柱状图（5 类资源叠加），数据源为 useCarbonStats.byMonthCategory
 * - 'line'：单/多资源折线图，数据源为 useCarbonStats.items
 */
import { computed, type Ref } from 'vue'
import type { ResourceCategory } from '@/client/types.gen'
import { categoryConfigMap } from '@/types/resource'
import { getThemeColors, getCategoryColor, withOpacity } from '@/utils/themeColors'
import { fmtNumber } from '@/utils/format'
import type { CarbonMonthItem, MonthCategoryEmission } from './useCarbonStats'

export interface EChartsOption {
  [key: string]: unknown
}

export type TrendMode = 'stacked' | 'line'

interface UseEmissionTrendChartOptions {
  mode: Ref<TrendMode>
  /** stacked 模式数据源（按月 × 类别） */
  byMonthCategory: Ref<MonthCategoryEmission[]>
  /** line 模式数据源（原始资源月度记录） */
  items: Ref<CarbonMonthItem[]>
  /** line 模式下要展示的资源 id 列表 */
  selectedResourceIds: Ref<number[]>
}

const CATEGORY_ORDER: ResourceCategory[] = ['labor', 'machinery', 'material', 'transport', 'others']

function formatMonth(month: string): string {
  const parts = month.split('-')
  return `${parseInt(parts[1] ?? '1', 10)}月`
}

function generateStackedOption(data: MonthCategoryEmission[]): EChartsOption {
  const C = getThemeColors()
  const TEXT_COLOR = withOpacity(C.baseContent, 0.65)
  const AXIS_COLOR = withOpacity(C.label, 0.25)
  const GRID_COLOR = withOpacity(C.label, 0.08)
  const TOOLTIP_BG = withOpacity(C.surfaceDeep, 0.95)
  const TOOLTIP_BORDER = withOpacity(C.primary, 0.3)
  const TOOLTIP_DIVIDER = withOpacity(C.baseContent, 0.15)
  const months = data.map((d) => d.month)

  const series = CATEGORY_ORDER.map((cat) => ({
    name: categoryConfigMap[cat].label,
    type: 'bar' as const,
    stack: 'total',
    emphasis: { focus: 'series' as const },
    itemStyle: { color: getCategoryColor(cat), borderRadius: [2, 2, 0, 0] },
    data: data.map((d) => Math.round((d.byCategory[cat] ?? 0) / 10) / 100), // kg -> t
  }))

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const },
      backgroundColor: TOOLTIP_BG,
      borderColor: TOOLTIP_BORDER,
      textStyle: { color: C.baseContent },
      formatter: (
        params: Array<{ seriesName: string; value: number; marker: string; dataIndex?: number }>,
      ) => {
        const total = params.reduce((sum, p) => sum + (p.value ?? 0), 0)
        const lines = params
          .map(
            (p) =>
              `<div style="display:flex;justify-content:space-between;gap:12px;"><span>${p.marker}${p.seriesName}</span><span>${fmtNumber(p.value, 2)} t</span></div>`,
          )
          .join('')
        const monthIdx = params[0]?.dataIndex ?? 0
        const monthLabel = formatMonth(months[monthIdx] ?? '')
        return `
          <div style="padding:4px 0;min-width:160px;">
            <div style="font-weight:600;margin-bottom:6px;">${monthLabel}</div>
            ${lines}
            <div style="border-top:1px solid ${TOOLTIP_DIVIDER};margin-top:6px;padding-top:6px;display:flex;justify-content:space-between;">
              <span style="color:${C.primary};">合计</span><span style="color:${C.primary};font-weight:600;">${fmtNumber(total, 2)} t</span>
            </div>
          </div>
        `
      },
    },
    legend: {
      data: CATEGORY_ORDER.map((c) => categoryConfigMap[c].label),
      textStyle: { color: TEXT_COLOR, fontSize: 11 },
      top: 0,
      right: 0,
      itemWidth: 12,
      itemHeight: 8,
    },
    grid: { left: 60, right: 20, top: 40, bottom: 40 },
    xAxis: {
      type: 'category' as const,
      data: months.map(formatMonth),
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisTick: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: TEXT_COLOR, fontSize: 11 },
    },
    yAxis: {
      type: 'value' as const,
      name: '碳排放 (tCO₂e)',
      nameLocation: 'middle' as const,
      nameGap: 35,
      nameTextStyle: { color: TEXT_COLOR, fontSize: 11 },
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisTick: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: TEXT_COLOR, fontSize: 11 },
      splitLine: { lineStyle: { color: GRID_COLOR } },
    },
    series,
  }
}

function generateLineOption(
  items: CarbonMonthItem[],
  selectedResourceIds: number[],
): EChartsOption {
  const C = getThemeColors()
  const TEXT_COLOR = withOpacity(C.baseContent, 0.65)
  const AXIS_COLOR = withOpacity(C.label, 0.25)
  const GRID_COLOR = withOpacity(C.label, 0.08)
  const TOOLTIP_BG = withOpacity(C.surfaceDeep, 0.95)
  const TOOLTIP_BORDER = withOpacity(C.primary, 0.3)
  const resourceMap = new Map<
    number,
    { name: string; category: ResourceCategory; byMonth: Map<string, number> }
  >()
  for (const item of items) {
    if (!resourceMap.has(item.resourceId)) {
      resourceMap.set(item.resourceId, {
        name: item.resourceName,
        category: item.category,
        byMonth: new Map(),
      })
    }
    const r = resourceMap.get(item.resourceId)!
    r.byMonth.set(item.month, (r.byMonth.get(item.month) ?? 0) + item.emission)
  }
  const months = Array.from(new Set(items.map((i) => i.month))).sort()
  const lineColors = [C.primary, C.amber, C.blue, C.indigo, C.red, C.emerald, C.cyan, '#ec4899']

  const series = selectedResourceIds.map((rid, idx) => {
    const r = resourceMap.get(rid)
    return {
      name: r?.name ?? `资源 #${rid}`,
      type: 'line' as const,
      smooth: true,
      symbol: 'circle' as const,
      symbolSize: 6,
      lineStyle: { width: 2 },
      itemStyle: { color: lineColors[idx % lineColors.length] ?? C.primary },
      data: months.map((m) => Math.round((r?.byMonth.get(m) ?? 0) / 10) / 100),
    }
  })

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: TOOLTIP_BG,
      borderColor: TOOLTIP_BORDER,
      textStyle: { color: C.baseContent },
    },
    legend: {
      data: series.map((s) => s.name),
      textStyle: { color: TEXT_COLOR, fontSize: 11 },
      top: 0,
      right: 0,
      itemWidth: 14,
      itemHeight: 8,
    },
    grid: { left: 60, right: 20, top: 40, bottom: 40 },
    xAxis: {
      type: 'category' as const,
      data: months.map(formatMonth),
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisTick: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: TEXT_COLOR, fontSize: 11 },
    },
    yAxis: {
      type: 'value' as const,
      name: '碳排放 (tCO₂e)',
      nameLocation: 'middle' as const,
      nameGap: 35,
      nameTextStyle: { color: TEXT_COLOR, fontSize: 11 },
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisTick: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: TEXT_COLOR, fontSize: 11 },
      splitLine: { lineStyle: { color: GRID_COLOR } },
    },
    series,
  }
}

export function useEmissionTrendChart(options: UseEmissionTrendChartOptions) {
  const chartOption = computed<EChartsOption>(() => {
    if (options.mode.value === 'stacked') {
      if (options.byMonthCategory.value.length === 0) return {}
      return generateStackedOption(options.byMonthCategory.value)
    }
    if (options.items.value.length === 0) return {}
    return generateLineOption(options.items.value, options.selectedResourceIds.value)
  })

  return { chartOption }
}
