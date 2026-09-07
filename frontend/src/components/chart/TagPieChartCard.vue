<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import type { ChartResp } from '@/client/types.gen'
import { useChartPieData } from '@/composables/useChartApi'
import { useTagPieChart, type PieSliceDatum } from '@/composables/useTagPieChart'
import { getSliceColor } from '@/utils/themeColors'
import { formatPct, formatTons, orderSlicesByChart } from '@/utils/chartSlices'
import { fmtNumber } from '@/utils/format'
import type { ChartPieMetric } from '@/composables/useChartApi'

/**
 * 标签饼图展示卡（S5）
 *
 * 图例为自定义行（名称 + t 值 + 占比），按 sortOrder 排序；零值切片隐藏。
 * 数据加载完成后向父级上报合计与隐藏切片数（供区块汇总条使用）。
 */
const props = defineProps<{
  chart: ChartResp
  /** 聚合指标：emission=碳排放（默认）/ cost=成本金额 */
  metric?: ChartPieMetric
}>()

const emit = defineEmits<{
  (e: 'summary', payload: { chartId: number; totalKg: number; hiddenCount: number }): void
}>()

const chartId = ref<number | null>(props.chart.id)
watch(
  () => props.chart.id,
  (id) => {
    chartId.value = id
  },
)

const metric = computed<ChartPieMetric>(() => props.metric ?? 'emission')
const { slices, totalEmission, isLoading } = useChartPieData(chartId, metric)

// 按 sortOrder 排序 → 过滤零值 → 上色
const displayed = computed<PieSliceDatum[]>(() =>
  orderSlicesByChart(slices.value)
    .filter((s) => (s.value ?? 0) > 0)
    .map((s, i) => ({ name: s.name, value: s.value, color: getSliceColor(i) })),
)

const isCost = computed(() => metric.value === 'cost')
const centerTotal = computed(() =>
  isCost.value
    ? `${fmtNumber(totalEmission.value / 10000, 2)} 万`
    : formatTons(totalEmission.value),
)

const { chartOption, totalKg } = useTagPieChart({
  slices: displayed,
  showLegend: false,
  centerTotal,
  centerLabel: isCost.value ? '成本' : 'tCO₂e',
})

function formatSliceValue(value: number): string {
  return isCost.value ? `${fmtNumber(value / 10000, 2)}万` : formatTons(value)
}

const finalOption = computed(() => ({
  ...chartOption.value,
  tooltip: {
    ...(chartOption.value.tooltip as object),
    formatter: (params: unknown) => {
      const p = params as { name: string; value: number; percent: number }
      if (!p) return ''
      const v = isCost.value ? `${fmtNumber(p.value / 10000, 2)} 万元` : formatTons(p.value)
      return `<b>${p.name}</b><br/>${v}（${p.percent}%）`
    },
  },
}))

// 隐藏零值切片数：绑定切片中统计为 0 或未返回的
const hiddenCount = computed(() => {
  const ordered = orderSlicesByChart(slices.value)
  const valueByName = new Map(ordered.map((s) => [s.name, s.value ?? 0]))
  return (props.chart.slices ?? []).filter((s) => (valueByName.get(s.name) ?? 0) <= 0).length
})

watch(
  () => [totalKg.value, hiddenCount.value, props.chart.id],
  () => {
    emit('summary', {
      chartId: props.chart.id,
      totalKg: totalKg.value,
      hiddenCount: hiddenCount.value,
    })
  },
  { immediate: true },
)

const isEmpty = computed(() => displayed.value.length === 0)
</script>

<template>
  <div class="panel p-4">
    <div class="flex items-center justify-between gap-3 mb-4">
      <h3 class="text-sm font-semibold text-base-content truncate">{{ chart.name }}</h3>
      <span class="material-symbols-outlined icon-sm text-fg-subtle shrink-0">open_in_new</span>
    </div>

    <div v-if="isLoading" class="h-48 flex items-center justify-center">
      <span class="loading loading-spinner loading-md text-primary" />
    </div>

    <!-- 空状态 -->
    <div
      v-else-if="isEmpty"
      class="h-48 flex flex-col items-center justify-center gap-2 text-center"
    >
      <div class="w-12 h-12 rounded-full bg-base-300/60 flex items-center justify-center">
        <span class="material-symbols-outlined icon-xl text-fg-subtle">pie_chart</span>
      </div>
      <p class="text-xs text-fg-muted">暂无碳排放数据</p>
      <p class="text-[11px] text-fg-subtle">录入资源使用量后自动展示</p>
    </div>

    <div v-else class="flex items-center gap-4">
      <div class="w-44 h-44 shrink-0">
        <v-chart :option="finalOption" :autoresize="true" class="w-full h-full" />
      </div>

      <!-- 自定义图例：名称 + 值 + 占比 -->
      <div class="flex-1 min-w-0 flex flex-col gap-1.5">
        <div v-for="slice in displayed" :key="slice.name" class="flex items-center gap-2 h-6">
          <span class="w-2 h-2 rounded-full shrink-0" :style="{ backgroundColor: slice.color }" />
          <span class="text-xs text-base-content truncate flex-1 min-w-0">{{ slice.name }}</span>
          <span class="text-[11px] font-num text-base-content shrink-0">
            {{ formatSliceValue(slice.value) }}
          </span>
          <span class="text-[11px] font-num text-fg-subtle w-11 text-right shrink-0">
            {{ formatPct(slice.value, totalKg) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
