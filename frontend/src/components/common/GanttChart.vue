<script setup lang="ts">
/**
 * 甘特图组件（纯展示）
 *
 * 职责：根据 startDay / duration 在时间轴上定位条形。
 * 不关心业务含义（关键路径、完成度等），所有语义信息由调用方通过 label / color / meta / tooltipFormatter 注入。
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { DefaultLabelFormatterCallbackParams } from 'echarts'
import { getThemeColors } from '@/utils/themeColors'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

// ──── 类型 ────────────────────────────────────────────────

/**
 * M 泛型：调用方自行决定 meta 的形状
 *
 * 用法示例：
 * ```ts
 * interface MyMeta {
 *   工序代号: string
 *   完成度: number
 *   是否关键路径: boolean
 *   备注: string
 * }
 * ```
 */
export interface GanttChartItem<M = unknown> {
  /** Y 轴标签（调用方拼装，组件原样展示） */
  label: string
  /** 条形起始位置（天） */
  startDay: number
  /** 工期（天） */
  duration: number
  /** 条形颜色（调用方决定着色逻辑） */
  color: string
  /** 任意附加数据，透传至 tooltipFormatter */
  meta?: M
}

export interface GanttChartProps<M = unknown> {
  items: GanttChartItem<M>[]
  totalDays: number
  /** 自定义 tooltip 内容；返回 HTML 字符串。不传则隐藏 tooltip。 */
  tooltipFormatter?: (item: GanttChartItem<M>) => string
  /** 条形宽度百分比，默认 60% */
  barWidth?: string
  /** Y 轴标签最大宽度（px），用于 grid.left 自适应 */
  labelWidth?: number
}

// ──── Props ───────────────────────────────────────────────

const {
  items,
  totalDays,
  tooltipFormatter,
  barWidth = '60%',
  labelWidth = 120,
} = defineProps<GanttChartProps>()

// ──── 计算 ────────────────────────────────────────────────

const xAxisInterval = computed(() => {
  if (totalDays <= 30) return 5
  if (totalDays <= 60) return 10
  if (totalDays <= 90) return 15
  return 20
})

interface GanttBarData {
  value: number
  itemStyle: { color: string }
  item: GanttChartItem
}

const chartOption = computed(() => {
  const categoryData = items.map((i) => i.label)
  const offsetData = items.map((i) => i.startDay)
  const barData = items.map((i) => ({
    value: i.duration,
    itemStyle: { color: i.color },
    item: i, // 原始引用，tooltip formatter 直接取用
  }))
  const themeColors = getThemeColors()
  return {
    tooltip: {
      trigger: 'item' as const,
      confine: true,
      formatter: (params: DefaultLabelFormatterCallbackParams) => {
        if (params.seriesIndex === 0) return ''
        const item = (params.data as GanttBarData).item
        if (!item || !tooltipFormatter) return ''
        return tooltipFormatter(item)
      },
    },
    grid: {
      left: labelWidth,
      right: 20,
      top: 20,
      bottom: 30,
    },
    xAxis: {
      type: 'value' as const,
      min: 0,
      max: totalDays,
      interval: xAxisInterval.value,
      axisLabel: { formatter: (v: number) => `第${v}天` },
      axisLine: { lineStyle: { color: themeColors.axis } },
      axisTick: { lineStyle: { color: themeColors.axis } },
      splitLine: { lineStyle: { color: themeColors.splitLine } },
    },
    yAxis: {
      type: 'category' as const,
      data: categoryData,
      inverse: true,
      axisLine: { lineStyle: { color: themeColors.axis } },
      axisTick: { show: false },
      axisLabel: { color: themeColors.label, fontSize: 12 },
    },
    series: [
      {
        name: 'offset',
        type: 'bar' as const,
        stack: 'gantt',
        data: offsetData,
        barWidth,
        itemStyle: { color: 'transparent', borderColor: 'transparent' },
        silent: true,
        tooltip: { show: false },
      },
      {
        name: 'duration',
        type: 'bar' as const,
        stack: 'gantt',
        data: barData,
        barWidth,
        itemStyle: { borderRadius: 4 },
        emphasis: { disabled: true },
      },
    ],
  }
})
</script>

<template>
  <div class="panel">
    <div class="p-0">
      <div class="h-96">
        <v-chart :option="chartOption" :autoresize="true" class="w-full h-full" />
      </div>
    </div>
  </div>
</template>
