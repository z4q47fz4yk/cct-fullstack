<script setup lang="ts">
/**
 * ConstructionTimelineChart - 施工阶段全景图（单实例多 grid）
 *
 * 三区共享同一条「第 N 天」时间轴（锚点 = 实际开工日，回退计划开工日）：
 *   1. 甘特：计划 vs 实际工序条（复用 GanttChart 的堆叠条技巧）
 *   2. 天气窄区：平均气温 / 降水两条折线（气温 ℃ 左轴，降水 mm 右轴）
 *   3. 碳排放：月度色带（custom series，支持分段堆叠，按维度由调用方切分）
 *
 * 纯展示组件：不关心业务语义，所有内容由调用方通过 props 注入。
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart, CustomChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { CustomSeriesRenderItem } from 'echarts'
import type { GanttChartItem } from '@/components/common/GanttChart.vue'
import { fmtEmission, fmtNumber } from '@/utils/format'
import { getThemeColors } from '@/utils/themeColors'

use([BarChart, LineChart, CustomChart, GridComponent, TooltipComponent, CanvasRenderer])

export interface EmissionSegment {
  name: string
  value: number
  color: string
}

export interface EmissionBand {
  /** 月份标签（如「3月」） */
  label: string
  /** 色带起始天（含） */
  startDay: number
  /** 色带结束天（不含） */
  endDay: number
  /** 当月碳排总量（kg） */
  totalKg: number
  /** 分段（按类别 / 资源堆叠；总量维度时仅一段） */
  segments: EmissionSegment[]
}

export interface WeatherPoint {
  /** 月份中点所在天 */
  day: number
  temperatureC: number | null
  precipitationMm: number | null
}

// Vue 3.5+ Reactive Props Destructure：解构即响应式，默认值在解构处声明。
const {
  ganttItems,
  ganttTooltipFormatter = undefined,
  ganttLabelWidth = 190,
  bands,
  weather,
  totalDays,
  /** 时间轴锚点日期（YYYY-MM-DD），为空时 x 轴回退为「第 N 天」 */
  anchorDate = null,
} = defineProps<{
  ganttItems: GanttChartItem<unknown>[]
  ganttTooltipFormatter?: (item: GanttChartItem<unknown>) => string
  ganttLabelWidth?: number
  bands: EmissionBand[]
  weather: WeatherPoint[]
  totalDays: number
  /** 时间轴锚点日期（YYYY-MM-DD），为空时 x 轴回退为「第 N 天」 */
  anchorDate?: string | null
}>()

const C = getThemeColors()

// ──── 布局尺寸 ─────────────────────────────────────────────
const GANTT_ROW = 34
const WEATHER_H = 90
const EMISSION_H = 220
const GAP = 14

const ganttHeight = computed(() => {
  const raw = Math.max(ganttItems.length, 1) * GANTT_ROW + 30
  return Math.min(Math.max(raw, 220), 480)
})

const chartHeight = computed(
  () => ganttHeight.value + (weather.length > 0 ? WEATHER_H + GAP : 0) + EMISSION_H + GAP + 30,
)

// ──── 时间轴 ───────────────────────────────────────────────
const xInterval = computed(() => {
  if (totalDays <= 30) return 5
  if (totalDays <= 60) return 10
  if (totalDays <= 90) return 15
  return 20
})

function fmtDay(day: number): string {
  if (!anchorDate) return `第${day}天`
  const d = new Date(new Date(anchorDate).getTime() + day * 86_400_000)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

const sharedXAxis = computed(() => ({
  type: 'value' as const,
  min: 0,
  max: totalDays,
  interval: xInterval.value,
  axisLine: { lineStyle: { color: C.axis } },
  axisTick: { lineStyle: { color: C.axis } },
  splitLine: { lineStyle: { color: C.splitLine } },
}))

// ──── 甘特：堆叠条（与 GanttChart 一致） ────────────────────
interface GanttBarData {
  value: number
  itemStyle: { color: string }
  item: GanttChartItem<unknown>
}

const ganttOffsetData = computed(() =>
  ganttItems.map((i) => ({ value: i.startDay, itemStyle: { color: 'transparent' } })),
)
const ganttBarData = computed<GanttBarData[]>(() =>
  ganttItems.map((i) => ({
    value: i.duration,
    itemStyle: { color: i.color, borderRadius: 4 },
    item: i,
  })),
)

// ──── 碳排放：custom series 月度色带 ────────────────────────
const maxBandKg = computed(() => Math.max(...bands.map((b) => b.totalKg), 1))

const emissionYMax = computed(() => Math.ceil(maxBandKg.value / 1000) * 1000)

const renderBand: CustomSeriesRenderItem = (params, api) => {
  const band = bands[params.dataIndex ?? 0]
  if (!band) return null
  // 累计值按 kg 直接传给 coord（y 轴为真实数据刻度，非归一化比例）
  let acc = 0
  const children = band.segments.map((seg) => {
    const y0 = acc
    acc += seg.value
    const y1 = acc
    const p0 = api.coord([band.startDay, y0] as [number, number]) as [number, number]
    const p1 = api.coord([band.endDay, y1] as [number, number]) as [number, number]
    return {
      type: 'rect' as const,
      shape: {
        x: p0[0],
        y: p1[1],
        width: Math.max(p1[0] - p0[0], 2),
        height: Math.max(p0[1] - p1[1], 2),
      },
      style: { fill: seg.color },
    }
  })
  return { type: 'group' as const, children }
}

// ──── 汇总 option ──────────────────────────────────────────
const chartOption = computed(() => {
  const hasWeather = weather.length > 0
  const top = 8
  const ganttTop = top
  const weatherTop = ganttTop + ganttHeight.value + GAP
  const emissionTop = weatherTop + (hasWeather ? WEATHER_H + GAP : 0)

  return {
    tooltip: {
      trigger: 'item' as const,
      confine: true,
      formatter: (params: { seriesIndex?: number; data?: unknown; value?: unknown }) => {
        if (params.seriesIndex === 0) return ''
        if (params.seriesIndex === 1) {
          const d = params.data as GanttBarData | undefined
          return ganttTooltipFormatter?.(d?.item as GanttChartItem<unknown>) ?? ''
        }
        if (params.seriesIndex === 2) {
          const v = (params.value as [number, number | null])[1]
          return v === null ? '' : `平均气温：${fmtNumber(v, 1)} ℃`
        }
        if (params.seriesIndex === 3) {
          const v = (params.value as [number, number | null])[1]
          return v === null ? '' : `降水：${fmtNumber(v, 1)} mm`
        }
        if (params.seriesIndex === 4) {
          const band = params.data as EmissionBand | undefined
          if (!band) return ''
          const rows = band.segments
            .map((s) => {
              const f = fmtEmission(s.value)
              return `<div style="display:flex;justify-content:space-between;gap:16px">
                <span style="display:inline-flex;align-items:center;gap:6px">
                  <i style="width:8px;height:8px;border-radius:2px;background:${s.color};display:inline-block"></i>${s.name}
                </span>
                <span style="font-variant-numeric:tabular-nums">${f.value} ${f.unit}</span>
              </div>`
            })
            .join('')
          const total = fmtEmission(band.totalKg)
          return `<div style="font-size:12px;line-height:1.8">
            <div style="font-weight:600;margin-bottom:2px">${band.label} · 碳排 ${total.value} ${total.unit}</div>
            ${rows}
          </div>`
        }
        return ''
      },
    },
    grid: [
      { left: ganttLabelWidth, right: 24, top: ganttTop, height: ganttHeight.value },
      {
        left: ganttLabelWidth,
        right: 24,
        top: weatherTop,
        height: hasWeather ? WEATHER_H : 0,
      },
      { left: ganttLabelWidth, right: 24, top: emissionTop, height: EMISSION_H },
    ],
    xAxis: [
      // 0: 甘特（不显示刻度文字，日期统一由底部碳排区展示）
      { ...sharedXAxis.value, axisLabel: { show: false }, gridIndex: 0 },
      {
        ...sharedXAxis.value,
        axisLabel: { show: false },
        splitLine: { show: false },
        gridIndex: 1,
      },
      {
        ...sharedXAxis.value,
        axisLabel: { color: C.label, formatter: (v: number) => fmtDay(v) },
        gridIndex: 2,
      },
    ],
    yAxis: [
      {
        type: 'category' as const,
        data: ganttItems.map((i) => i.label),
        inverse: true,
        axisLine: { lineStyle: { color: C.axis } },
        axisTick: { show: false },
        axisLabel: {
          color: C.label,
          fontSize: 12,
          width: ganttLabelWidth - 12,
          overflow: 'truncate',
        },
        gridIndex: 0,
      },
      {
        type: 'value' as const,
        name: '℃',
        nameTextStyle: { color: C.label },
        axisLabel: { color: C.label, fontSize: 10 },
        splitLine: { lineStyle: { color: C.splitLine } },
        gridIndex: 1,
      },
      {
        type: 'value' as const,
        name: 'mm',
        nameTextStyle: { color: C.label },
        axisLabel: { color: C.label, fontSize: 10 },
        splitLine: { show: false },
        gridIndex: 1,
      },
      {
        type: 'value' as const,
        min: 0,
        max: emissionYMax.value,
        axisLabel: { color: C.label, formatter: (v: number) => `${fmtNumber(v / 1000, 0)}t` },
        splitLine: { lineStyle: { color: C.splitLine } },
        gridIndex: 2,
      },
    ],
    series: [
      {
        name: 'offset',
        type: 'bar' as const,
        stack: 'gantt',
        barWidth: '55%',
        data: ganttOffsetData.value,
        silent: true,
        tooltip: { show: false },
        xAxisIndex: 0,
        yAxisIndex: 0,
      },
      {
        name: 'duration',
        type: 'bar' as const,
        stack: 'gantt',
        barWidth: '55%',
        data: ganttBarData.value,
        emphasis: { disabled: true },
        xAxisIndex: 0,
        yAxisIndex: 0,
      },
      {
        name: '平均气温',
        type: 'line' as const,
        data: weather.map((w) => [w.day, w.temperatureC] as [number, number | null]),
        smooth: true,
        showSymbol: true,
        symbolSize: 5,
        connectNulls: false,
        itemStyle: { color: C.accel },
        lineStyle: { color: C.accel, width: 2 },
        xAxisIndex: 1,
        yAxisIndex: 1,
      },
      {
        name: '降水',
        type: 'line' as const,
        data: weather.map((w) => [w.day, w.precipitationMm] as [number, number | null]),
        smooth: true,
        showSymbol: true,
        symbolSize: 5,
        connectNulls: false,
        itemStyle: { color: C.info },
        lineStyle: { color: C.info, width: 2 },
        xAxisIndex: 1,
        yAxisIndex: 2,
      },
      {
        name: '碳排',
        type: 'custom' as const,
        data: bands,
        renderItem: renderBand,
        xAxisIndex: 2,
        yAxisIndex: 3,
      },
    ],
  }
})
</script>

<template>
  <div :style="{ height: `${chartHeight}px` }">
    <VChart :option="chartOption" autoresize class="w-full h-full" />
  </div>
</template>
