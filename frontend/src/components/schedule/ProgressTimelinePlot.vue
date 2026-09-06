<script setup lang="ts">
/**
 * ProgressTimelinePlot - 施工进度 Plotly 主图（三区：甘特 / 碳排柱 / 天气）
 *
 * 纯渲染壳：业务数据在页面层组装为 ProgressPlotData 传入，本组件负责
 * 动态加载 plotly.js 并管理容器实例（newPlot 首渲 / react 增量更新 / purge）。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadPlotly, type PlotlyApi } from '@/utils/plotly'
import { buildProgressPlotFigure, type ProgressPlotData } from '@/composables/useProgressPlotFigure'

const props = defineProps<{
  data: ProgressPlotData
  /** 图表高度（px） */
  height?: number
}>()

const el = ref<HTMLDivElement | null>(null)
let plotly: PlotlyApi | null = null
let rendered = false

async function render() {
  if (!el.value) return
  if (!plotly) plotly = await loadPlotly()
  const fig = buildProgressPlotFigure(props.data)
  // 窄类型对象即 plotly 运行时接受的普通 figure；此处按包 API 形态断言
  const p = plotly as unknown as {
    newPlot: (e: HTMLElement, d: unknown, l: unknown, c?: unknown) => Promise<unknown>
    react: (e: HTMLElement, d: unknown, l: unknown, c?: unknown) => Promise<unknown>
  }
  if (rendered) {
    await p.react(el.value, fig.data, fig.layout, { responsive: true })
  } else {
    await p.newPlot(el.value, fig.data, fig.layout, { responsive: true })
    rendered = true
  }
}

watch(
  () => props.data,
  () => {
    void render()
  },
  { deep: true },
)

onMounted(() => {
  void render()
})

onBeforeUnmount(() => {
  if (plotly && el.value) {
    const p = plotly as unknown as { purge: (e: HTMLElement) => void }
    p.purge(el.value)
  }
  rendered = false
})
</script>

<template>
  <div ref="el" class="w-full" :style="{ height: `${height ?? 480}px` }" />
</template>
