<script setup lang="ts">
/**
 * ResourceUsageChart - 统计 tab 的「实际 vs 计划」分组条形图
 *
 * 数据源：useResourceEmissionStats（并行拉取 ACTUAL + PLANNED 两个维度的月度排放）
 *
 * x 轴：资源名
 * y 轴：碳排放（kgCO₂e）
 * 每个资源两根相邻柱子：实际 / 计划
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getThemeColors } from '@/utils/themeColors'
import { fmtNumber } from '@/utils/format'
import type { ResourceResp } from '@/client/types.gen'
import { useResourceEmissionStats } from '@/composables/useResourceEmissionStats'
import ErrorState from '@/components/common/ErrorState.vue'

use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const { resources } = defineProps<{
  /** 当前选中的资源（来自 ResourceUsageChartFilters） */
  resources: ResourceResp[]
}>()

const { byResource, isLoading, isNotFound, error, refresh } = useResourceEmissionStats()

// 所选资源 id 集合
const selectedIds = computed(() => new Set(resources.map((r) => r.id)))

// 过滤到所选资源 + 按资源名排序（让 X 轴稳定）
const filteredRows = computed(() =>
  byResource.value
    .filter((r) => selectedIds.value.has(r.resourceId))
    .sort((a, b) => a.resourceName.localeCompare(b.resourceName, 'zh-CN')),
)

const chartOption = computed(() => {
  const rows = filteredRows.value
  const names = rows.map((r) => r.resourceName)
  // kg → t，保留 2 位小数
  const actual = rows.map((r) => Math.round((r.actual / 1000) * 100) / 100)
  const planned = rows.map((r) => Math.round((r.planned / 1000) * 100) / 100)
  const tc = getThemeColors()

  return {
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const },
      confine: true,
      formatter: (params: unknown) => {
        const arr = params as Array<{
          name: string
          seriesName: string
          value: number
          dataIndex: number
        }>
        if (!arr || arr.length === 0) return ''
        const first = arr[0]
        if (!first) return ''
        const row = rows[first.dataIndex]
        if (!row) return ''
        const lines = [`<b>${row.resourceName}</b>`]
        for (const p of arr) {
          lines.push(`${p.seriesName}：${fmtNumber(p.value, 2)} tCO₂e`)
        }
        const a = arr.find((p) => p.seriesName === '实际')
        const p = arr.find((p) => p.seriesName === '计划')
        if (a && p) {
          const diff = a.value - p.value
          const sign = diff >= 0 ? '+' : ''
          const color = diff >= 0 ? tc.error : tc.success
          lines.push(
            `<span style="color:${color}">实际 − 计划：${sign}${fmtNumber(diff, 2)} tCO₂e</span>`,
          )
        }
        return lines.join('<br/>')
      },
    },
    legend: {
      data: ['实际', '计划'],
      textStyle: { color: tc.label },
      top: 0,
    },
    grid: {
      left: 60,
      right: 20,
      top: 40,
      bottom: 80,
    },
    xAxis: {
      type: 'category' as const,
      data: names,
      axisLabel: {
        color: tc.label,
        rotate: 30,
        fontSize: 11,
        interval: 0,
      },
      axisLine: { lineStyle: { color: tc.axis } },
      axisTick: { lineStyle: { color: tc.axis } },
    },
    yAxis: {
      type: 'value' as const,
      name: 'tCO₂e',
      nameTextStyle: { color: tc.label, fontSize: 11 },
      nameLocation: 'end' as const,
      axisLabel: { color: tc.label, fontSize: 11 },
      axisLine: { lineStyle: { color: tc.axis } },
      axisTick: { lineStyle: { color: tc.axis } },
      splitLine: { lineStyle: { color: tc.splitLine } },
    },
    series: [
      {
        name: '计划',
        type: 'bar' as const,
        data: planned,
        itemStyle: { color: tc.info, borderRadius: [4, 4, 0, 0] },
        barGap: '20%',
        barCategoryGap: '40%',
      },
      {
        name: '实际',
        type: 'bar' as const,
        data: actual,
        itemStyle: { color: tc.success, borderRadius: [4, 4, 0, 0] },
        barGap: '20%',
      },
    ],
  }
})
</script>

<template>
  <!-- 加载 -->
  <div v-if="isLoading" class="flex justify-center py-8">
    <span class="loading loading-spinner loading-lg text-primary"></span>
  </div>

  <!-- 404 / 数据不存在 -->
  <ErrorState
    v-else-if="isNotFound"
    title="暂无碳排放数据"
    description="后端未找到本项目的月度排放记录，请先在「资源使用」中录入数据后再查看"
    icon="eco"
    @retry="refresh"
  />

  <!-- 通用错误 -->
  <ErrorState
    v-else-if="error && !isNotFound"
    title="加载失败"
    description="无法获取碳排放数据，请检查网络连接"
    @retry="refresh"
  />

  <!-- 未选资源 -->
  <div v-else-if="resources.length === 0" class="p-4 panel">
    <div class="flex flex-col items-center justify-center py-8">
      <div class="w-16 h-16 rounded-full bg-base-300 flex items-center justify-center mb-3">
        <span class="material-symbols-outlined icon-2xl text-base-content/30">bar_chart</span>
      </div>
      <p class="text-fg-subtle">请先选择需要对比的资源</p>
    </div>
  </div>

  <!-- 选了资源但无数据 -->
  <div v-else-if="filteredRows.length === 0" class="p-4 panel">
    <div class="flex flex-col items-center justify-center py-8">
      <div class="w-16 h-16 rounded-full bg-base-300 flex items-center justify-center mb-3">
        <span class="material-symbols-outlined icon-2xl text-base-content/30">eco</span>
      </div>
      <p class="text-fg-subtle">所选资源暂无实际或计划排放数据</p>
    </div>
  </div>

  <!-- 正常态：分组条形图 -->
  <div v-else class="panel">
    <div class="p-0">
      <div class="h-96">
        <v-chart :option="chartOption" :autoresize="true" class="w-full h-full" />
      </div>
    </div>
  </div>
</template>
