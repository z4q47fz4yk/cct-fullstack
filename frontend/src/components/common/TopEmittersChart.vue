<script setup lang="ts">
/**
 * Top N 高排放资源横向柱状图（纯展示）
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useTopEmittersChart } from '@/composables/useTopEmittersChart'
import type { ResourceEmission } from '@/composables/useCarbonStats'
import ChartEmptyState from './ChartEmptyState.vue'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const { topEmitters, selectedResourceId } = defineProps<{
  topEmitters: ResourceEmission[]
  selectedResourceId: number | null
}>()

const emit = defineEmits<{
  'select-resource': [resourceId: number]
}>()

const emittersRef = computed(() => topEmitters)
const selectedRef = computed(() => selectedResourceId)

const { chartOption } = useTopEmittersChart({
  topEmitters: emittersRef,
  selectedResourceId: selectedRef,
})

const isEmpty = computed(() => topEmitters.length === 0)

function handleChartClick(params: { dataIndex?: number }) {
  const idx = params.dataIndex
  if (idx === undefined) return
  const item = topEmitters[idx]
  if (!item) return
  emit('select-resource', item.resourceId)
}
</script>

<template>
  <div class="panel">
    <div class="p-4">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-base font-semibold text-base-content">Top N 高排放资源</h2>
        <p class="text-xs text-neutral-content/40">点击行查看月度走势</p>
      </div>

      <div class="h-96 relative">
        <ChartEmptyState v-if="isEmpty" icon="bar_chart_4_bars" title="暂无资源数据" />
        <v-chart
          v-else
          :option="chartOption"
          :autoresize="true"
          class="w-full h-full"
          @click="handleChartClick"
        />
      </div>
    </div>
  </div>
</template>
