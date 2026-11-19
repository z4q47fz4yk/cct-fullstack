<script setup lang="ts">
import { ref } from 'vue'
import { useChartApi } from '@/composables/useChartApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { formatHttpError } from '@/utils/error'
import type { ChartResp } from '@/client/types.gen'
import ChartCard from '@/components/chart/ChartCard.vue'
import ChartEditorDrawer from '@/components/chart/ChartEditorDrawer.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import LoadingState from '@/components/common/LoadingState.vue'
import PageHead from '@/components/common/PageHead.vue'

definePage({
  meta: {
    title: '碳排放图表',
    description: '用切片（标签组合 + 或/且命中）配置饼图',
    icon: 'pie_chart',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 8,
  },
})

const {
  charts,
  isLoading,
  error,
  refresh,
  createChart,
  updateChart,
  setChartSlices,
  deleteChart,
  isSubmitting,
} = useChartApi()
const { currentProjectId } = useProjectContext()
const { confirmDanger } = useConfirm()
const { notifySuccess } = useToast()

// ─── 编辑器 ────────────────────────────────────────────────

const showEditor = ref(false)
const editingChart = ref<ChartResp | null>(null)
const formError = ref('')

function openCreate() {
  editingChart.value = null
  formError.value = ''
  showEditor.value = true
}

function openEdit(chart: ChartResp) {
  editingChart.value = chart
  formError.value = ''
  showEditor.value = true
}

async function handleSaved(payload: {
  name: string
  description: string
  chartType: string
  slices: Array<{ name: string; tags: Array<{ tagId: number; group?: number }> }>
}) {
  formError.value = ''
  try {
    let chartId: number
    if (editingChart.value) {
      await updateChart({
        path: { project_id: currentProjectId.value!, id: editingChart.value.id },
        body: {
          name: payload.name,
          description: payload.description,
          chartType: payload.chartType,
        },
      })
      chartId = editingChart.value.id
      notifySuccess('图表已更新')
    } else {
      const created = await createChart({
        path: { project_id: currentProjectId.value! },
        body: {
          name: payload.name,
          description: payload.description,
          chartType: payload.chartType,
        },
      })
      chartId = created.id
      notifySuccess('图表已创建')
    }
    await setChartSlices({
      path: { project_id: currentProjectId.value!, id: chartId },
      body: { slices: payload.slices },
    })
    showEditor.value = false
  } catch (e) {
    formError.value = formatHttpError(e, '保存失败，请重试')
    console.error('Save chart failed:', e)
  }
}

function closeEditor() {
  showEditor.value = false
}

// ─── 删除 ──────────────────────────────────────────────────

async function handleDelete(chart: ChartResp) {
  const { confirmed } = await confirmDanger(`确定要删除图表「${chart.name}」吗？`)
  if (!confirmed) return
  try {
    await deleteChart({ path: { project_id: currentProjectId.value!, id: chart.id } })
    notifySuccess('图表已删除')
  } catch (e) {
    console.error('Delete chart failed:', e)
  }
}
</script>

<template>
  <ErrorState
    v-if="error"
    title="加载失败"
    description="无法获取图表列表，请检查网络连接"
    @retry="refresh"
  />

  <div v-else class="space-y-4">
    <!-- 页头（设计稿 view-charts page-head：新建图表） -->
    <PageHead title="碳排放图表" subtitle="按标签切片配置饼图，展示碳排/成本分布">
      <button class="btn btn-primary gap-1" :disabled="isLoading" @click="openCreate">
        <span class="material-symbols-outlined icon-sm">add</span>
        新建图表
      </button>
    </PageHead>

    <!-- 卡片网格（设计稿 grid3） -->
    <div v-if="isLoading" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <LoadingState variant="skeleton" class="h-64" />
      <LoadingState variant="skeleton" class="h-64" />
      <LoadingState variant="skeleton" class="h-64" />
    </div>

    <div v-else-if="charts.length === 0" class="panel py-8 text-center">
      <div
        class="w-14 h-14 rounded-full bg-base-300/60 flex items-center justify-center mx-auto mb-3"
      >
        <span class="material-symbols-outlined icon-2xl text-fg-subtle">pie_chart</span>
      </div>
      <p class="text-fg-muted text-sm">暂无图表定义</p>
      <p class="text-xs text-fg-subtle mt-1">点击右上角「新建图表」创建第一个饼图配置</p>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 items-start">
      <ChartCard
        v-for="chart in charts"
        :key="chart.id"
        :chart="chart"
        @edit="openEdit"
        @delete="handleDelete"
      />
      <!-- 虚线新建卡（设计稿） -->
      <div
        class="panel border-dashed flex flex-col items-center justify-center gap-2 text-fg-muted min-h-56 cursor-pointer hover:text-primary hover:border-primary/50 transition-colors"
        role="button"
        tabindex="0"
        @click="openCreate"
        @keydown.enter="openCreate"
      >
        <span class="material-symbols-outlined icon-xl text-fg-subtle">add</span>
        <span class="text-sm">新建图表</span>
      </div>
    </div>

    <!-- 编辑器抽屉 -->
    <ChartEditorDrawer
      :show="showEditor"
      :chart="editingChart"
      :is-submitting="isSubmitting"
      :error="formError"
      @saved="handleSaved"
      @cancel="closeEditor"
    />
  </div>
</template>
