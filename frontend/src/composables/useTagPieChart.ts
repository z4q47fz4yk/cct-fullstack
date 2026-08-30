import { computed } from 'vue'
import type { Ref } from 'vue'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GraphicComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getThemeColors } from '@/utils/themeColors'
import { fmtNumber } from '@/utils/format'

use([PieChart, TooltipComponent, LegendComponent, GraphicComponent, CanvasRenderer])

/** 饼图切片数据（value 单位 kgCO₂e） */
export interface PieSliceDatum {
  name: string
  value: number
  color: string
}

interface UseTagPieChartOptions {
  slices: Ref<PieSliceDatum[]>
  /** 是否显示右侧图例（展示卡开启，迷你预览关闭） */
  showLegend?: boolean
  /** 中心主数值文案（如 "949.6"），缺省显示合计 */
  centerTotal?: Ref<string>
  /** 中心副文案，缺省 "tCO₂e" */
  centerLabel?: string
}

/**
 * 标签碳排放饼图 option 构造
 *
 * - 数值单位 kgCO₂e，tooltip 换算为 t 展示
 * - 中心显示合计（graphic 两行文字，随主题色）
 * - 图例为右侧纵向，随主题切换
 */
export function useTagPieChart(options: UseTagPieChartOptions) {
  const { slices, showLegend = false, centerTotal, centerLabel = 'tCO₂e' } = options

  const totalKg = computed(() => slices.value.reduce((sum, s) => sum + s.value, 0))

  const chartOption = computed(() => {
    const tc = getThemeColors()
    const centerText = centerTotal?.value ?? fmtNumber(totalKg.value / 1000, 2)
    const data = slices.value.map((s) => ({
      name: s.name,
      value: s.value,
      itemStyle: { color: s.color },
    }))

    const graphicLeft = showLegend ? '39%' : '50%'
    const graphicTop = showLegend ? '50%' : '50%'

    return {
      tooltip: {
        trigger: 'item' as const,
        confine: true,
        formatter: (params: unknown) => {
          const p = params as { name: string; value: number; percent: number }
          if (!p) return ''
          return `<b>${p.name}</b><br/>${fmtNumber(p.value / 1000, 2)} t（${p.percent}%）`
        },
      },
      legend: showLegend
        ? {
            orient: 'vertical' as const,
            right: 12,
            top: 'center' as const,
            textStyle: { color: tc.label, fontSize: 12 },
            itemWidth: 10,
            itemHeight: 10,
            icon: 'circle' as const,
          }
        : undefined,
      graphic: [
        {
          type: 'text' as const,
          left: graphicLeft,
          top: graphicTop,
          style: {
            text: centerLabel,
            fontSize: 10,
            fill: tc.label,
            textAlign: 'center' as const,
            textVerticalAlign: 'bottom' as const,
            y: -10,
          },
        },
        {
          type: 'text' as const,
          left: graphicLeft,
          top: graphicTop,
          style: {
            text: centerText,
            fontSize: 15,
            fontWeight: 'bold' as const,
            fill: tc.baseContent,
            textAlign: 'center' as const,
            textVerticalAlign: 'top' as const,
            y: 12,
          },
        },
      ],
      series: [
        {
          name: '碳排放',
          type: 'pie' as const,
          radius: showLegend ? ['42%', '68%'] : ['45%', '75%'],
          center: showLegend ? ['38%', '50%'] : ['50%', '50%'],
          label: { show: false },
          emphasis: {
            label: {
              show: true,
              fontSize: 13,
              fontWeight: 'bold' as const,
            },
          },
          data,
        },
      ],
    }
  })

  return { chartOption, totalKg }
}
