<script setup lang="ts">
/**
 * 帕累托前沿图表组件
 *
 * 支持四种视图：
 * - 成本 vs 工期（2D）
 * - 成本 vs 碳排放（2D）
 * - 工期 vs 碳排放（2D）
 * - 成本 vs 工期 vs 碳排放（3D）
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import 'echarts-gl'
import { useParetoChart, type ViewMode } from '@/composables/useParetoChart'
import type { OptimizeSolution } from '@/client/types.gen'

// 注册 ECharts 组件
use([ScatterChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const { selectedId, solutions } = defineProps<{
  selectedId: number | null
  solutions: OptimizeSolution[]
}>()

const emit = defineEmits<{
  'update:selectedId': [id: number | null]
}>()

// 使用 composable
// Vue 3.5 解构的 props 在运行时是 ref，但 TS 类型仍为原值；用 computed 包一层以满足 composable 的 Ref 参数类型
const { viewMode, chartOption, is3DView, setViewMode } = useParetoChart(
  computed(() => solutions),
  computed(() => selectedId),
)

// 视图选项
const viewOptions: { value: ViewMode; label: string }[] = [
  { value: 'cost-duration', label: '成本-工期' },
  { value: 'cost-emission', label: '成本-碳排' },
  { value: 'duration-emission', label: '工期-碳排' },
  { value: '3d', label: '3D 视图' },
]

// 处理图表点击事件
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function handleChartClick(params: any) {
  if (params.data?.id !== undefined) {
    emit('update:selectedId', params.data.id === selectedId ? null : params.data.id)
  }
}

// 空状态判断
const isEmpty = computed(() => solutions.length === 0)
</script>

<template>
  <div class="panel h-full p-4">
    <!-- 标题和视图切换 -->
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-base font-semibold text-base-content">帕累托前沿</h2>
        <p class="text-xs text-fg-muted mt-0.5">工期 · 成本 · 碳排放 多目标解集分布</p>
      </div>

      <!-- 视图切换 Tab -->
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

    <!-- 图表容器 -->
    <div class="h-80 relative">
      <!-- 加载/空状态 -->
      <ChartEmptyState
        v-if="isEmpty"
        icon="scatter_plot"
        title="暂无解集数据"
        description="请先运行一次优化"
      />

      <!-- 图表 -->
      <v-chart
        v-else
        :option="chartOption"
        :autoresize="true"
        class="w-full h-full"
        @click="handleChartClick"
      />
    </div>

    <!-- 图例 -->
    <div class="flex items-center justify-center gap-4 mt-4">
      <div class="flex items-center gap-2">
        <div
          class="w-2.5 h-2.5 rounded-full"
          style="background: rgba(129, 140, 248, 0.6); box-shadow: 0 0 8px rgba(129, 140, 248, 0.5)"
        ></div>
        <span class="text-xs text-fg-muted">帕累托解</span>
      </div>
      <div class="flex items-center gap-2">
        <div
          class="w-2.5 h-2.5 rounded-full"
          :style="{
            background: `var(--color-cyan, #22d3ee)`,
            'box-shadow':
              '0 0 8px color-mix(in oklch, var(--color-cyan, #22d3ee) 60%, transparent)',
          }"
        ></div>
        <span class="text-xs text-fg-muted">选中方案</span>
      </div>
      <div v-if="is3DView" class="flex items-center gap-2 ml-4">
        <span class="text-xs text-fg-subtle">拖拽旋转 · 滚轮缩放</span>
      </div>
    </div>
  </div>
</template>
