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
  <Teleport defer to="#header-actions">
    <button class="btn btn-primary gap-1 px-5" :disabled="isLoading" @click="openCreate">
      <span class="material-symbols-outlined icon-sm">add</span>
      新建图表
    </button>
  </Teleport>

  <ErrorState
    v-if="error"
    title="加载失败"
    description="无法获取图表列表，请检查网络连接"
    @retry="refresh"
  />

  <div v-else class="space-y-4">
    <!-- 说明 -->
    <section class="panel px-4 py-3 flex items-center gap-3">
      <span class="material-symbols-outlined text-violet-400 icon-md shrink-0">pie_chart</span>
      <p class="text-xs text-fg-muted leading-relaxed">
        每个切片 =
        若干标签组：同组标签需同时命中（且），组间命中任一（或）；支持「资源类别」默认标签
        （人工/机械/材料/运输/其他）按资源类别命中。
        切片重叠时同一用量会重复计入，可在「数据体检」检查。
      </p>
    </section>

    <!-- 卡片网格 -->
    <div v-if="isLoading" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
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

    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
      <ChartCard
        v-for="chart in charts"
        :key="chart.id"
        :chart="chart"
        @edit="openEdit"
        @delete="handleDelete"
      />
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
