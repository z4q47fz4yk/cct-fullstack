<script setup lang="ts">
/**
 * 碳排放趋势图（堆叠柱 / 折线 双模式）
 *
 * 纯展示组件；调用方通过 props 注入数据并通过 update:* 接收交互。
 * 数据源类型与 useCarbonStats 保持一致。
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { MonthlyResourceEmission, ResourceCategory } from '@/client/types.gen'
import { categoryConfigMap } from '@/types/resource'
import type { MonthCategoryEmission } from '@/composables/useCarbonStats'
import { useEmissionTrendChart, type TrendMode } from '@/composables/useEmissionTrendChart'
import ChartEmptyState from './ChartEmptyState.vue'

use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const { mode, byMonthCategory, items, selectedResourceIds, availableResources } = defineProps<{
  mode: TrendMode
  byMonthCategory: MonthCategoryEmission[]
  items: MonthlyResourceEmission[]
  selectedResourceIds: number[]
  availableResources: Array<{ id: number; name: string; category: ResourceCategory }>
}>()

const emit = defineEmits<{
  'update:mode': [mode: TrendMode]
  'update:selectedResourceIds': [ids: number[]]
}>()

const modeRef = computed({
  get: () => mode,
  set: (v) => emit('update:mode', v),
})
const byMonthCategoryRef = computed(() => byMonthCategory)
const itemsRef = computed(() => items)
const idsRef = computed({
  get: () => selectedResourceIds,
  set: (v) => emit('update:selectedResourceIds', v),
})

const { chartOption } = useEmissionTrendChart({
  mode: modeRef,
  byMonthCategory: byMonthCategoryRef,
  items: itemsRef,
  selectedResourceIds: idsRef,
})

const isEmpty = computed(() =>
  mode === 'stacked' ? byMonthCategory.length === 0 : items.length === 0,
)

function toggleResource(id: number) {
  const cur = new Set(selectedResourceIds)
  if (cur.has(id)) cur.delete(id)
  else cur.add(id)
  emit('update:selectedResourceIds', Array.from(cur))
}

function categoryLabel(c: ResourceCategory): string {
  return categoryConfigMap[c].label
}
</script>

<template>
  <div class="panel">
    <div class="p-4">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-base font-semibold text-base-content">碳排放趋势</h2>

        <div class="tabs tabs-boxed tabs-sm">
          <button
            class="tab"
            :class="{ 'tab-active': mode === 'stacked' }"
            @click="emit('update:mode', 'stacked')"
          >
            按月堆叠
          </button>
          <button
            class="tab"
            :class="{ 'tab-active': mode === 'line' }"
            @click="emit('update:mode', 'line')"
          >
            单资源走势
          </button>
        </div>
      </div>

      <div v-if="mode === 'line'" class="mb-3">
        <details class="collapse collapse-arrow bg-base-300/40 rounded-lg">
          <summary class="collapse-title text-sm font-medium min-h-0 py-2">
            资源选择 ({{ selectedResourceIds.length }}/{{ availableResources.length }})
          </summary>
          <div class="collapse-content">
            <div class="flex flex-wrap gap-2 pt-1">
              <button
                v-for="r in availableResources"
                :key="r.id"
                class="badge badge-sm cursor-pointer transition-colors"
                :class="
                  selectedResourceIds.includes(r.id)
                    ? 'badge-primary'
                    : 'badge-outline text-fg-muted'
                "
                @click="toggleResource(r.id)"
              >
                {{ r.name }}<span class="ml-1 opacity-60">{{ categoryLabel(r.category) }}</span>
              </button>
            </div>
          </div>
        </details>
      </div>

      <div class="h-80 relative">
        <ChartEmptyState v-if="isEmpty" icon="show_chart" title="暂无月度数据" />
        <v-chart v-else :option="chartOption" :autoresize="true" class="w-full h-full" />
      </div>
    </div>
  </div>
</template>
