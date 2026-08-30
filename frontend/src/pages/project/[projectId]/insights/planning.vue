<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useQuery } from '@pinia/colada'
import { useRoute } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import StatCard from '@/components/common/StatCard.vue'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import { useInsightsStore } from '@/stores/insights'
import { usePlanApi } from '@/composables/usePlanApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useConfirm } from '@/composables/useConfirm'
import { notifySuccess, notifyInfo, notifyWarning, notifyError } from '@/composables/useToast'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { listResourcesQuery, listOptimizeRecordResultQuery } from '@/client/@pinia/colada.gen'
import type {
  MeasureCreate,
  MeasureKind,
  MeasureResp,
  MeasureStatus,
  OptimizeSolution,
  PlanEstimateResp,
  PlanEstimateRequest,
  ResourceResp,
} from '@/client/types.gen'
import { categoryConfigMap } from '@/types/resource'
import { fmtEmission, fmtWanYuan, fmtNumber } from '@/utils/format'
import { getThemeColors } from '@/utils/themeColors'
import { formatHttpError } from '@/utils/error'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

definePage({
  meta: {
    title: '计划编制',
    icon: 'edit_calendar',
    showInNav: true,
    parentName: '/project/[projectId]/insights',
    group: '计划阶段',
    navOrder: 2,
  },
})

const store = useInsightsStore()
const route = useRoute()
const { currentProjectId } = useProjectContext()
const { confirmDanger } = useConfirm()
const {
  plan,
  isPlanMissing,
  measures,
  isLoadingMeasures,
  estimatePlan,
  savePlan,
  savePlanDraft,
  createMeasureItem,
  updateMeasureItem,
  deleteMeasureItem,
  isEstimating,
  isSaving,
  isSavingDraft,
  refreshMeasures,
} = usePlanApi()

// ──── 资源列表（措施表单选资源用） ─────────────────────────
const resourcesQuery = useQuery(() => ({
  ...listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { page: 1, per_page: FETCH_ALL_PAGE_SIZE },
  }),
  enabled: !!currentProjectId.value,
}))
const resources = computed<ResourceResp[]>(() => resourcesQuery.state.value?.data?.items ?? [])
const resourceById = computed(() => new Map(resources.value.map((r) => [r.id, r])))

// ──── ① 方案摘要：运行 + 解选择 ───────────────────────────
const runs = computed(() => store.records.filter((r) => r.status === 'SUCCESS'))
const selectedRunId = ref<string | null>(null)
const queryRunId = typeof route.query.runId === 'string' ? route.query.runId : null
const querySolutionId =
  typeof route.query.solutionId === 'string' ? Number(route.query.solutionId) : null

watch(
  runs,
  (list) => {
    if (!selectedRunId.value && list.length > 0) {
      selectedRunId.value = queryRunId ?? store.currentRunId ?? list[0]?.id ?? null
    }
  },
  { immediate: true },
)

const solutionsQuery = useQuery(() => ({
  ...listOptimizeRecordResultQuery({
    path: { project_id: currentProjectId.value!, id: selectedRunId.value ?? '' },
    query: { page: 1, per_page: FETCH_ALL_PAGE_SIZE },
  }),
  enabled: !!currentProjectId.value && !!selectedRunId.value,
}))
const solutions = computed<OptimizeSolution[]>(() => solutionsQuery.state.value?.data?.items ?? [])

const selectedSolutionId = ref<number | null>(null)
watch(
  solutions,
  (list) => {
    if (!list.some((s) => s.id === selectedSolutionId.value)) {
      selectedSolutionId.value =
        querySolutionId !== null && list.some((s) => s.id === querySolutionId)
          ? querySolutionId
          : (list[0]?.id ?? null)
    }
  },
  { immediate: true },
)

const selectedSolution = computed<OptimizeSolution | null>(
  () => solutions.value.find((s) => s.id === selectedSolutionId.value) ?? null,
)

// ──── ④ 预估计算 ──────────────────────────────────────────
const estimateResult = ref<PlanEstimateResp | null>(null)
const estimateError = ref<string | null>(null)

function buildRequest(): PlanEstimateRequest {
  return {
    sourceRunId: selectedRunId.value ?? undefined,
    sourceSolutionId: selectedSolutionId.value ?? undefined,
    measures: measures.value.map((m) => ({ id: m.id, kind: m.kind, resourceIds: m.resourceIds })),
  }
}

async function handleEstimate() {
  if (!selectedSolutionId.value) {
    notifyWarning({ title: '请先选择方案', description: '从上方方案摘要中选择一个 NSGA-II 解' })
    return
  }
  estimateError.value = null
  try {
    estimateResult.value = await estimatePlan(buildRequest())
    notifySuccess({ title: '预估完成', description: '已按当前措施重算工期 / 成本 / 碳排' })
  } catch (e) {
    const msg = formatHttpError(e)
    estimateError.value = msg
    console.error('Estimate failed:', e)
  }
}

async function handleSave(draft: boolean) {
  if (!selectedSolutionId.value) {
    notifyWarning({ title: '请先选择方案' })
    return
  }
  try {
    if (draft) {
      await savePlanDraft(buildRequest())
      notifyInfo({ title: '草稿已保存', description: '草稿不参与聚合与践行度计算' })
    } else {
      await savePlan(buildRequest())
      notifySuccess({ title: '已保存为计划基线', description: '评价阶段将以该基线进行对比' })
    }
  } catch (e) {
    const msg = formatHttpError(e)
    console.error('Save plan failed:', e)
    notifyError({ title: draft ? '保存草稿失败' : '保存基线失败', description: msg })
  }
}

// 与原方案的差异
const deltas = computed(() => {
  const src = selectedSolution.value
  const est = estimateResult.value
  if (!src || !est) return null
  return {
    duration: est.totalDuration - src.duration,
    cost: est.totalCost - src.cost,
    emission: est.totalEmission - src.emission,
  }
})

// ──── 月度碳排分布（预估结果聚合） ────────────────────────
const monthlyEmission = computed<{ month: string; kg: number }[]>(() => {
  const m = new Map<string, number>()
  for (const item of estimateResult.value?.monthly ?? []) {
    m.set(item.month, (m.get(item.month) ?? 0) + item.emission)
  }
  return Array.from(m.entries())
    .map(([month, kg]) => ({ month: month.slice(5, 7) + '月', kg }))
    .sort((a, b) => a.month.localeCompare(b.month))
})

const C = getThemeColors()
const monthlyChartOption = computed(() => ({
  grid: { left: 48, right: 16, top: 24, bottom: 28 },
  tooltip: {
    trigger: 'axis',
    formatter: (params: unknown) => {
      const p = params as { name: string; value: number }[]
      const v = p[0]?.value ?? 0
      const f = fmtEmission(v)
      return `${p[0]?.name ?? ''}<br/>碳排：${f.value} ${f.unit}`
    },
  },
  xAxis: {
    type: 'category',
    data: monthlyEmission.value.map((m) => m.month),
    axisLabel: { color: C.label },
  },
  yAxis: {
    type: 'value',
    axisLabel: {
      color: C.label,
      formatter: (v: number) => `${fmtNumber(Math.round(v / 1000), 0)}t`,
    },
    splitLine: { lineStyle: { color: C.splitLine } },
  },
  series: [
    {
      type: 'bar',
      data: monthlyEmission.value.map((m) => m.kg),
      itemStyle: { color: C.indigo, borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 28,
    },
  ],
}))

// ──── ③ 减碳措施：列表 + 表单弹窗 ─────────────────────────
const showMeasureModal = ref(false)
const editingMeasureId = ref<number | null>(null)
const form = reactive({
  kind: 'ADD' as MeasureKind,
  resourceId: null as number | null,
  plannedResourceId: null as number | null,
  actualResourceId: null as number | null,
  status: 'PLANNED' as MeasureStatus,
  scale: null as number | null,
  implementedDate: null as string | null,
  note: null as string | null,
})
const formError = ref<string | null>(null)

const addResources = computed(() => resources.value.filter((r) => (r.carbonFactor ?? 0) < 0))
const replaceResources = computed(() => resources.value)

function openCreate() {
  editingMeasureId.value = null
  Object.assign(form, {
    kind: 'ADD' as MeasureKind,
    resourceId: null,
    plannedResourceId: null,
    actualResourceId: null,
    status: 'PLANNED' as MeasureStatus,
    scale: null,
    implementedDate: null,
    note: null,
  })
  formError.value = null
  showMeasureModal.value = true
}

function openEdit(m: MeasureResp) {
  editingMeasureId.value = m.id
  Object.assign(form, {
    kind: m.kind,
    resourceId: m.kind === 'ADD' ? (m.resourceIds[0] ?? null) : null,
    plannedResourceId: m.kind === 'REPLACE' ? (m.resourceIds[0] ?? null) : null,
    actualResourceId: m.kind === 'REPLACE' ? (m.resourceIds[1] ?? null) : null,
    status: m.status,
    scale: m.scale ?? null,
    implementedDate: m.implementedDate ?? null,
    note: m.note ?? null,
  })
  formError.value = null
  showMeasureModal.value = true
}

async function handleSubmitMeasure() {
  formError.value = null
  const resourceIds =
    form.kind === 'ADD'
      ? form.resourceId
        ? [form.resourceId]
        : []
      : form.plannedResourceId && form.actualResourceId
        ? [form.plannedResourceId, form.actualResourceId]
        : []
  if (resourceIds.length === 0) {
    formError.value = form.kind === 'ADD' ? '请选择负碳因子资源' : '请选择计划资源与实际资源'
    return
  }
  if (form.kind === 'REPLACE' && resourceIds[0] === resourceIds[1]) {
    formError.value = '计划资源与实际资源不能相同'
    return
  }
  const body: MeasureCreate = {
    kind: form.kind,
    resourceIds,
    status: form.status,
    scale: form.scale,
    implementedDate: form.implementedDate,
    note: form.note,
  }
  try {
    if (editingMeasureId.value) {
      await updateMeasureItem(editingMeasureId.value, body)
    } else {
      await createMeasureItem(body)
    }
    await refreshMeasures()
    showMeasureModal.value = false
    notifySuccess({ title: editingMeasureId.value ? '措施已更新' : '措施已添加' })
  } catch (e) {
    formError.value = formatHttpError(e)
    console.error('Save measure failed:', e)
  }
}

async function handleDeleteMeasure(m: MeasureResp) {
  const r = await confirmDanger('确定要删除该措施吗？删除后需重新预估。', '删除措施')
  if (!r.confirmed) return
  try {
    await deleteMeasureItem(m.id)
    await refreshMeasures()
    notifyInfo({ title: '已删除措施' })
  } catch (e) {
    console.error('Delete measure failed:', e)
  }
}

function measureResourceNames(m: MeasureResp): string {
  return m.resourceIds.map((id) => resourceById.value.get(id)?.name ?? `资源#${id}`).join(' → ')
}

function statusLabel(s: MeasureStatus): string {
  return s === 'PLANNED' ? '计划中' : s === 'IMPLEMENTED' ? '已实施' : '未实施'
}

const kindOptions: ReadonlyArray<SegmentOption<MeasureKind>> = [
  { value: 'ADD', label: '添加类', icon: 'add_circle' },
  { value: 'REPLACE', label: '替换类', icon: 'swap_horiz' },
]
</script>

<template>
  <div class="h-full flex flex-col gap-4 overflow-y-auto">
    <!-- ① 方案摘要 -->
    <section class="panel p-4">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-semibold text-base-content">① 方案摘要</h2>
        <span v-if="selectedRunId" class="text-xs text-fg-subtle font-mono">
          来源 · Run #{{ selectedRunId.slice(0, 8) }} · NSGA-II
        </span>
      </div>
      <div class="flex gap-3 flex-wrap mb-4">
        <label class="fieldset flex-1 min-w-48">
          <span class="fieldset-legend">优化运行</span>
          <select v-model="selectedRunId" class="select select-bordered">
            <option v-for="r in runs" :key="r.id" :value="r.id">
              {{ r.name || `Run ${r.id.slice(0, 8)}` }}
            </option>
          </select>
        </label>
        <label class="fieldset flex-1 min-w-48">
          <span class="fieldset-legend">推荐方案</span>
          <select v-model.number="selectedSolutionId" class="select select-bordered">
            <option v-for="(s, i) in solutions" :key="s.id" :value="s.id">
              方案 #{{ i + 1 }} · 工期 {{ fmtNumber(s.duration, 1) }}天 · 成本
              {{ fmtWanYuan(s.cost) }}万
            </option>
          </select>
        </label>
      </div>
      <div v-if="selectedSolution" class="grid grid-cols-3 gap-4">
        <StatCard
          label="工期"
          :value="fmtNumber(selectedSolution.duration, 1)"
          unit="天"
          icon="schedule"
          color="primary"
        />
        <StatCard
          label="总成本"
          :value="fmtWanYuan(selectedSolution.cost)"
          unit="万元"
          icon="payments"
          color="neutral"
        />
        <StatCard
          label="总碳排"
          :value="fmtEmission(selectedSolution.emission).value"
          :unit="fmtEmission(selectedSolution.emission).unit"
          icon="eco"
          color="success"
        />
      </div>
      <ChartEmptyState
        v-else-if="!solutionsQuery.asyncStatus.value"
        icon="scatter_plot"
        title="暂无方案"
        description="请先在「优化结果」中运行一次 NSGA-II 优化"
      />
    </section>

    <!-- ③ 减碳措施 -->
    <section class="panel p-4">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-semibold text-base-content">③ 减碳措施</h2>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <span class="material-symbols-outlined icon-sm">add</span>
          添加措施
        </button>
      </div>
      <div v-if="measures.length === 0 && !isLoadingMeasures" class="py-6 text-center">
        <p class="text-sm text-fg-muted">
          暂无措施。添加光伏（负碳因子资源）或设备替换，预估计算会自动计入节碳。
        </p>
      </div>
      <div class="space-y-2">
        <div
          v-for="m in measures"
          :key="m.id"
          class="flex items-center gap-3 rounded-lg border border-base-content/10 bg-base-content/[0.02] px-3 py-2.5"
        >
          <span
            class="text-xs font-medium px-2 py-0.5 rounded-full shrink-0"
            :class="m.kind === 'ADD' ? 'bg-success/15 text-success' : 'bg-info/15 text-info'"
          >
            {{ m.kind === 'ADD' ? '添加' : '替换' }}
          </span>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-base-content truncate">
              {{ measureResourceNames(m) }}
            </p>
            <p class="text-xs text-fg-subtle mt-0.5">
              {{ statusLabel(m.status) }}
              <template v-if="m.scale"> · 规模 {{ m.scale }}</template>
              <template v-if="m.implementedDate"> · 实施 {{ m.implementedDate }}</template>
            </p>
          </div>
          <div class="text-right shrink-0">
            <p class="text-[11px] text-fg-subtle">预估节碳</p>
            <p class="text-sm font-semibold font-num text-success">
              {{ m.estimatedSaving < 0 ? '−' : '+'
              }}{{ fmtNumber(Math.abs(m.estimatedSaving) / 1000, 2) }} t
            </p>
          </div>
          <div class="flex gap-1 shrink-0">
            <button class="btn btn-ghost btn-xs" @click="openEdit(m)">编辑</button>
            <button class="btn btn-ghost btn-xs text-error" @click="handleDeleteMeasure(m)">
              删除
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- ④ 预估计算 -->
    <section class="panel p-4">
      <div class="flex items-center justify-between mb-3 gap-4 flex-wrap">
        <div class="flex items-center gap-3">
          <h2 class="text-sm font-semibold text-base-content">④ 预估计算</h2>
          <span v-if="!isPlanMissing && plan" class="text-xs text-fg-subtle font-mono">
            当前基线：{{ plan.status === 'PLANNED' ? '正式' : '草稿' }} · 保存于
            {{ new Date(plan.updatedAt).toLocaleDateString() }}
          </span>
          <span
            v-if="plan?.isStale"
            class="text-[11px] font-medium px-2 py-0.5 rounded-full bg-warning/15 text-warning"
          >
            数据已变更，建议重新预估
          </span>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-ghost btn-sm" :disabled="isSavingDraft" @click="handleSave(true)">
            保存草稿
          </button>
          <button class="btn btn-primary btn-sm" :disabled="isEstimating" @click="handleEstimate">
            <span v-if="isEstimating" class="loading loading-spinner loading-sm"></span>
            <span v-else class="material-symbols-outlined icon-sm">calculate</span>
            重新预估
          </button>
          <button class="btn btn-success btn-sm" :disabled="isSaving" @click="handleSave(false)">
            <span v-if="isSaving" class="loading loading-spinner loading-sm"></span>
            <span v-else class="material-symbols-outlined icon-sm">save</span>
            保存为计划基线
          </button>
        </div>
      </div>

      <p v-if="estimateError" class="text-xs text-error mb-3">预估失败：{{ estimateError }}</p>

      <div v-if="estimateResult && selectedSolution" class="space-y-4">
        <div class="grid grid-cols-3 gap-4">
          <StatCard
            label="调整后工期"
            :value="fmtNumber(estimateResult.totalDuration, 1)"
            unit="天"
            icon="schedule"
            color="primary"
          />
          <StatCard
            label="调整后总成本"
            :value="fmtWanYuan(estimateResult.totalCost)"
            unit="万元"
            icon="payments"
            color="neutral"
          />
          <StatCard
            label="调整后总碳排"
            :value="fmtEmission(estimateResult.totalEmission).value"
            :unit="fmtEmission(estimateResult.totalEmission).unit"
            icon="eco"
            color="success"
          />
        </div>

        <div v-if="deltas" class="flex gap-6 px-1 text-xs font-mono">
          <span :class="deltas.duration <= 0 ? 'text-success' : 'text-error'">
            工期 {{ deltas.duration > 0 ? '+' : '' }}{{ fmtNumber(deltas.duration, 1) }} 天
          </span>
          <span :class="deltas.cost <= 0 ? 'text-success' : 'text-error'">
            成本 {{ deltas.cost > 0 ? '+' : '' }}{{ fmtWanYuan(deltas.cost) }} 万
          </span>
          <span :class="deltas.emission <= 0 ? 'text-success' : 'text-error'">
            碳排 {{ deltas.emission > 0 ? '+' : '' }}{{ fmtNumber(deltas.emission / 1000, 2) }} t
          </span>
        </div>

        <div v-if="monthlyEmission.length > 0" class="h-52">
          <VChart :option="monthlyChartOption" autoresize />
        </div>
        <p class="text-xs text-fg-subtle">月度碳排分布（含措施生效后）</p>
      </div>

      <ChartEmptyState
        v-else
        icon="calculate"
        title="尚未预估"
        description="选择方案并确认措施后，点击「重新预估」查看调整结果"
      />
    </section>

    <!-- 措施表单弹窗 -->
    <BaseModal
      v-model:open="showMeasureModal"
      :title="editingMeasureId ? '编辑措施' : '添加措施'"
      class="max-w-xl"
    >
      <div class="space-y-4">
        <div>
          <span class="fieldset-legend">措施类型</span>
          <SegmentControl v-model="form.kind" :options="kindOptions" class="mt-1" />
        </div>

        <template v-if="form.kind === 'ADD'">
          <label class="fieldset">
            <span class="fieldset-legend">负碳因子资源（如光伏）</span>
            <select v-model.number="form.resourceId" class="select select-bordered">
              <option :value="null" disabled>请选择资源</option>
              <option v-for="r in addResources" :key="r.id" :value="r.id">
                {{ r.name }}（{{ categoryConfigMap[r.category].label }} · 因子
                {{ r.carbonFactor }}）
              </option>
            </select>
          </label>
          <p v-if="addResources.length === 0" class="text-xs text-warning">
            尚无负碳因子资源，请先在「资源管理」中创建碳因子为负的资源（如光伏）。
          </p>
        </template>

        <template v-else>
          <div class="grid grid-cols-2 gap-3">
            <label class="fieldset">
              <span class="fieldset-legend">计划资源（旧）</span>
              <select v-model.number="form.plannedResourceId" class="select select-bordered">
                <option :value="null" disabled>请选择</option>
                <option v-for="r in replaceResources" :key="r.id" :value="r.id">
                  {{ r.name }}
                </option>
              </select>
            </label>
            <label class="fieldset">
              <span class="fieldset-legend">实际资源（新）</span>
              <select v-model.number="form.actualResourceId" class="select select-bordered">
                <option :value="null" disabled>请选择</option>
                <option v-for="r in replaceResources" :key="r.id" :value="r.id">
                  {{ r.name }}
                </option>
              </select>
            </label>
          </div>
        </template>

        <div class="grid grid-cols-2 gap-3">
          <label class="fieldset">
            <span class="fieldset-legend">状态</span>
            <select v-model="form.status" class="select select-bordered">
              <option value="PLANNED">计划中</option>
              <option value="IMPLEMENTED">已实施</option>
              <option value="ABANDONED">未实施</option>
            </select>
          </label>
          <label class="fieldset">
            <span class="fieldset-legend">规模 / 数量</span>
            <input
              v-model.number="form.scale"
              type="number"
              class="input input-bordered"
              placeholder="可选"
            />
          </label>
        </div>

        <label class="fieldset">
          <span class="fieldset-legend">实施日期（实际节碳自该日起算）</span>
          <input v-model="form.implementedDate" type="date" class="input input-bordered" />
        </label>

        <label class="fieldset">
          <span class="fieldset-legend">备注</span>
          <input v-model="form.note" type="text" class="input input-bordered" placeholder="可选" />
        </label>

        <p v-if="formError" class="text-xs text-error">{{ formError }}</p>
      </div>
      <template #actions>
        <button class="btn btn-ghost" @click="showMeasureModal = false">取消</button>
        <button class="btn btn-primary" @click="handleSubmitMeasure">
          {{ editingMeasureId ? '保存修改' : '添加' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>
