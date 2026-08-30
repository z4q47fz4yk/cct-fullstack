<script setup lang="ts">
/**
 * 对比帕累托前沿图表组件（串行 vs 并行）
 *
 * 两个运行的原始解集叠加展示：幸存解按运行着色，被支配/重复解半透明，
 * 选中解白色描边。支持 2D / 3D 视图切换。
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import 'echarts-gl'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import { useCompareParetoChart, type ViewMode } from '@/composables/useCompareParetoChart'
import type { CompareRunGroup } from '@/composables/useParetoCompare'
import { getThemeColors, hexToRgb } from '@/utils/themeColors'

use([ScatterChart, GridComponent, TooltipComponent, CanvasRenderer])

const {
  groups,
  dominatedIds,
  selectedId,
  hasMerged = false,
} = defineProps<{
  groups: CompareRunGroup[]
  dominatedIds: Set<number>
  selectedId: number | null
  /** 是否已生成对比（merge 完成），决定图例如何拆幸存/被支配 */
  hasMerged?: boolean
}>()

const emit = defineEmits<{
  'update:selectedId': [id: number | null]
}>()

const { viewMode, chartOption, is3DView, setViewMode } = useCompareParetoChart(
  computed(() => groups),
  computed(() => dominatedIds),
  computed(() => selectedId),
  computed(() => hasMerged),
)

const viewOptions: { value: ViewMode; label: string }[] = [
  { value: 'cost-duration', label: '成本-工期' },
  { value: 'cost-emission', label: '成本-碳排' },
  { value: 'duration-emission', label: '工期-碳排' },
  { value: '3d', label: '3D 视图' },
]

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function handleChartClick(params: any) {
  if (params.data?.id !== undefined) {
    emit('update:selectedId', params.data.id === selectedId ? null : params.data.id)
  }
}

const isEmpty = computed(() => groups.every((g) => g.solutions.length === 0))

/** 图例：每运行总数（生成对比后拆幸存/被支配）+ 被支配总数 */
const legend = computed(() => {
  const C = getThemeColors()
  return {
    entries: groups.map((g) => {
      const total = g.solutions.length
      const dominated = g.solutions.filter((s) => dominatedIds.has(s.id)).length
      return {
        label: g.label,
        color: g.color === 'indigo' ? C.indigo : C.cyan,
        survivor: total - dominated,
        total,
      }
    }),
    dominatedTotal: groups.reduce(
      (acc, g) => acc + g.solutions.filter((s) => dominatedIds.has(s.id)).length,
      0,
    ),
  }
})

/** 被支配/重复图例：与图表一致，各运行色 12% 不透明度 */
const dominatedDots = computed(() => {
  const C = getThemeColors()
  return [
    { background: `rgba(${hexToRgb(C.indigo)}, 0.12)`, border: C.indigo },
    { background: `rgba(${hexToRgb(C.cyan)}, 0.12)`, border: C.cyan },
  ]
})
</script>

<template>
  <div class="h-full flex flex-col">
    <div class="flex items-center justify-between mb-4 shrink-0">
      <div>
        <h2 class="text-base font-semibold text-base-content">帕累托前沿（对比）</h2>
        <p class="text-xs text-fg-muted mt-0.5">两个运行解集叠加 · 半透明为被支配解</p>
      </div>

      <div class="tabs tabs-boxed tabs-sm bg-transparent">
        <button
          v-for="opt in viewOptions"
          :key="opt.value"
          class="tab"
          :class="{ 'tab-active': viewMode === opt.value }"
          @click="setViewMode(opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>
    </div>

    <div class="h-80 relative">
      <ChartEmptyState
        v-if="isEmpty"
        icon="compare_arrows"
        title="暂无对比数据"
        description="请选择两个已完成运行并生成对比"
      />

      <v-chart
        v-else
        :option="chartOption"
        :autoresize="true"
        class="w-full h-full"
        @click="handleChartClick"
      />
    </div>

    <div class="flex items-center justify-center gap-4 mt-4 flex-wrap">
      <div v-for="entry in legend.entries" :key="entry.label" class="flex items-center gap-2">
        <div class="w-2.5 h-2.5 rounded-full" :style="{ background: entry.color }"></div>
        <span class="text-xs text-fg-muted">
          {{
            hasMerged
              ? `${entry.label}（幸存 ${entry.survivor}/${entry.total}）`
              : `${entry.label}（${entry.total}）`
          }}
        </span>
      </div>
      <div v-if="hasMerged && legend.dominatedTotal > 0" class="flex items-center gap-2">
        <div class="flex gap-1">
          <div
            v-for="(dot, idx) in dominatedDots"
            :key="idx"
            class="w-2.5 h-2.5 rounded-full border"
            :style="{ background: dot.background, borderColor: dot.border }"
          ></div>
        </div>
        <span class="text-xs text-fg-muted">被支配/重复（{{ legend.dominatedTotal }}）</span>
      </div>
      <div v-if="is3DView" class="flex items-center gap-2 ml-4">
        <span class="text-xs text-fg-subtle">拖拽旋转 · 滚轮缩放</span>
      </div>
    </div>
  </div>
</template>
