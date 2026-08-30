/**
 * Top N 高排放资源横向柱状图配置 composable
 *
 * 数据源：useCarbonStats.byResource (ResourceEmission[])
 */
import { computed, type Ref } from 'vue'
import { categoryConfigMap } from '@/types/resource'
import { getThemeColors, getCategoryColor, withOpacity } from '@/utils/themeColors'
import { fmtNumber } from '@/utils/format'
import type { ResourceEmission } from './useCarbonStats'

export interface EChartsOption {
  [key: string]: unknown
}

interface UseTopEmittersChartOptions {
  topEmitters: Ref<ResourceEmission[]>
  selectedResourceId: Ref<number | null>
}

export function useTopEmittersChart(options: UseTopEmittersChartOptions) {
  const chartOption = computed<EChartsOption>(() => {
    const items = options.topEmitters.value
    if (items.length === 0) return {}

    const C = getThemeColors()
    const TEXT_COLOR = withOpacity(C.baseContent, 0.65)
    const AXIS_COLOR = withOpacity(C.label, 0.25)
    const GRID_COLOR = withOpacity(C.label, 0.08)
    const TOOLTIP_BG = withOpacity(C.surfaceDeep, 0.95)
    const TOOLTIP_BORDER = withOpacity(C.primary, 0.3)

    const categories = items.map((i) => i.resourceName)
    const values = items.map((i) => Math.round(i.emissionKg / 10) / 100)

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis' as const,
        axisPointer: { type: 'shadow' as const },
        backgroundColor: TOOLTIP_BG,
        borderColor: TOOLTIP_BORDER,
        textStyle: { color: C.baseContent },
        formatter: (params: Array<{ dataIndex: number }>) => {
          const p = params[0]
          if (!p) return ''
          const item = items[p.dataIndex]
          if (!item) return ''
          return `
            <div style="padding:4px 0;">
              <div style="font-weight:600;margin-bottom:4px;">${item.resourceName}</div>
              <div>类别：<span style="color:${getCategoryColor(item.category)}">${categoryConfigMap[item.category].label}</span></div>
              <div>排放：<span style="color:${C.success};">${fmtNumber(item.emissionKg / 1000, 2)} t</span></div>
            </div>
          `
        },
      },
      grid: { left: 100, right: 50, top: 10, bottom: 30 },
      xAxis: {
        type: 'value' as const,
        name: 'tCO₂e',
        nameTextStyle: { color: TEXT_COLOR, fontSize: 11 },
        nameLocation: 'end' as const,
        axisLine: { lineStyle: { color: AXIS_COLOR } },
        axisTick: { lineStyle: { color: AXIS_COLOR } },
        axisLabel: { color: TEXT_COLOR, fontSize: 11 },
        splitLine: { lineStyle: { color: GRID_COLOR } },
      },
      yAxis: {
        type: 'category' as const,
        data: categories,
        inverse: true,
        axisLine: { lineStyle: { color: AXIS_COLOR } },
        axisTick: { show: false },
        axisLabel: { color: TEXT_COLOR, fontSize: 12 },
      },
      series: [
        {
          type: 'bar' as const,
          data: items.map((item, idx) => ({
            value: values[idx] ?? 0,
            itemStyle: {
              color: getCategoryColor(item.category),
              borderRadius: [0, 4, 4, 0],
              opacity:
                options.selectedResourceId.value === null ||
                options.selectedResourceId.value === item.resourceId
                  ? 1
                  : 0.4,
              borderWidth: options.selectedResourceId.value === item.resourceId ? 2 : 0,
              borderColor: '#fff',
            },
          })),
          barWidth: '60%',
          label: {
            show: true,
            position: 'right' as const,
            color: TEXT_COLOR,
            fontSize: 11,
            formatter: (params: { value: number }) => `${fmtNumber(params.value, 1)} t`,
          },
        },
      ],
    }
  })

  return { chartOption }
}
