<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useInsightsStore } from '@/stores/insights'
import GanttChart, { type GanttChartItem } from '@/components/common/GanttChart.vue'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import ParetoChart from '@/components/optimization/ParetoChart.vue'
import CompareParetoChart from '@/components/optimization/CompareParetoChart.vue'
import CompareRunsPanel from '@/components/optimization/CompareRunsPanel.vue'
import CompareStatsPanel from '@/components/optimization/CompareStatsPanel.vue'
import ParetoSolutionsTable from '@/components/optimization/ParetoSolutionsTable.vue'
import SaveWeightPresetModal from '@/components/optimization/SaveWeightPresetModal.vue'
import OptimizationConfig from '@/components/optimization/OptimizationConfig.vue'
import RunStatusBar from '@/components/optimization/RunStatusBar.vue'
import { sortTasksForGantt } from '@/utils/schedule'
import { fmtNumber, fmtWanYuan } from '@/utils/format'
import { formatHttpError } from '@/utils/error'
import { validateRunConfig, type RunConfigKey } from '@/utils/runConfig'
import type { RunResp, RunStatusEnum, TaskMode } from '@/client/types.gen'
import { notifyError, notifyInfo, notifySuccess, notifyWarning } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { useProjectContext } from '@/composables/useProjectContext'
import { useDiagnosticsApi } from '@/composables/useDiagnosticsApi'
import { getThemeColors } from '@/utils/themeColors'
import { scoreSolutions } from '@/utils/paretoScore'
import { useParetoCompare, snapshotTasksToTaskResp } from '@/composables/useParetoCompare'
import {
  DEFAULT_PARETO_WEIGHTS,
  type ParetoWeights,
  type WeightPreset,
} from '@/types/paretoWeights'

definePage({
  meta: {
    title: '优化结果',
    icon: 'scatter_plot',
    showInNav: true,
    parentName: '/project/[projectId]/insights',
    group: '计划阶段',
    navOrder: 1,
  },
})

const store = useInsightsStore()
const { confirmWarn, confirmDanger } = useConfirm()
const { currentProjectId } = useProjectContext()
const router = useRouter()
const route = useRoute()

function handlePlanEntry() {
  if (!store.selectedSolutionId) return
  const projectId = (route.params as { projectId?: string }).projectId ?? ''
  router.push({
    name: '/project/[projectId]/insights/planning',
    params: { projectId },
    query: {
      runId: store.currentRunId ?? '',
      solutionId: String(store.selectedSolutionId),
    },
  })
}

// ──── 运行对比（选择两个历史运行，自动合并解集） ──────────────

const {
  compareRunIds,
  compareSelectedSolutionId,
  groups,
  rawSolutions,
  mergedSolutions,
  dominatedIds,
  isMerging,
  hasMerged,
  runLabel,
  runById,
  selectedCompareSolution,
  snapshot,
  isLoadingSnapshot,
} = useParetoCompare()

const compareActive = computed(() => compareRunIds.value.length === 2)

// ──── 权重预设（由调用方决定数量与文案） ─────────────────────
const WEIGHT_PRESETS: readonly WeightPreset[] = [
  { label: '等权', values: { ...DEFAULT_PARETO_WEIGHTS } },
  { label: '时间优先', values: { duration: 100, cost: 0, emission: 0 } },
  { label: '成本优先', values: { duration: 0, cost: 100, emission: 0 } },
  { label: '低碳优先', values: { duration: 0, cost: 0, emission: 100 } },
  { label: '时间+成本', values: { duration: 50, cost: 50, emission: 0 } },
  { label: '成本+低碳', values: { duration: 0, cost: 50, emission: 50 } },
]

// ──── 保存预设弹窗 ──────────────────────────────────────────
const showSavePreset = ref(false)
const presetExternalError = ref<string | null>(null)

// 每次打开弹窗时清空外部错误
watch(showSavePreset, (v) => {
  if (v) presetExternalError.value = null
})

function handleAddPreset() {
  showSavePreset.value = true
}

function confirmAddPreset(name: string, weights: ParetoWeights) {
  const trimmed = name.trim()
  // 与内置预设重名也不允许（store 只查自定义列表）
  if (WEIGHT_PRESETS.some((p) => p.label === trimmed)) {
    presetExternalError.value = '已存在同名预设，请使用其他名称'
    return
  }
  const ok = store.addCustomPreset(trimmed, weights)
  if (!ok) {
    presetExternalError.value = '已存在同名预设，请使用其他名称'
    return
  }
  store.weights = weights
  showSavePreset.value = false
  notifySuccess({ title: '预设已保存', description: trimmed })
}

async function handleRemovePreset(id: string, label: string) {
  const r = await confirmDanger(`确定要删除预设「${label}」吗？此操作不可撤销。`, '删除预设')
  if (r.confirmed) {
    const removed = store.customPresets.find((p) => p.id === id)
    store.removeCustomPreset(id)
    notifyInfo({ title: '已删除预设', description: label })
    // 删除的是当前正在使用的权重：排序不受影响，但提示用户后续无法再一键恢复
    if (
      removed &&
      removed.values.duration === store.weights.duration &&
      removed.values.cost === store.weights.cost &&
      removed.values.emission === store.weights.emission
    ) {
      notifyWarning({ title: '已删除当前使用的权重预设', description: '当前排序权重保持不变' })
    }
  }
}

async function handleStopOptimization() {
  const r = await confirmWarn('确定要停止当前优化任务吗？已生成的代际将丢失。', '停止优化')
  if (r.confirmed) {
    await store.stopOptimization()
  }
}

async function handleResetOptimization() {
  const r = await confirmWarn('重新开始将清空当前运行结果与选中方案。', '重新开始')
  if (r.confirmed) {
    store.resetOptimization()
  }
}

// ──── 开始优化（要求先填写运行名称） ─────────────────────────

const runName = ref('')
const runNameTouched = ref(false)
// 参数修改面板展开态（内联于本页，取代独立的「优化配置」页）
const showConfig = ref(false)

// 数据体检被动入口：仅有零碳因子警告时显示一行小链接，不阻断流程
const { zeroFactorCount: diagZeroFactorCount } = useDiagnosticsApi(() => 'ALL')

async function handleStartOptimization() {
  const name = runName.value.trim()
  if (!name) return
  // 提交前字段级校验：参数非法（如种群/代数为 0）时不发请求，展开参数面板并给出可见提示
  const configErrors = validateRunConfig(store.config)
  const errorKeys = Object.keys(configErrors) as RunConfigKey[]
  if (errorKeys.length > 0) {
    showConfig.value = true
    notifyWarning({
      title: '优化参数有误',
      description: configErrors[errorKeys[0]!] ?? '请检查优化参数',
    })
    return
  }
  try {
    await store.startOptimization(name)
    runName.value = ''
    runNameTouched.value = false
  } catch (e) {
    console.error('Start optimization failed:', e)
    notifyError({ title: '启动优化失败', description: formatHttpError(e) })
  }
}

// ──── 历史运行：查看过去的优化结果（仅已完成运行） ────────────

const pastRunSelect = ref('')

// 仅展示 SUCCESS 运行（结果可查看），按创建时间倒序
const successRuns = computed(() =>
  [...store.records]
    .filter((r) => r.status === 'SUCCESS')
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
)

const latestSuccessRunId = computed(() => successRuns.value[0]?.id ?? null)

function loadPastRun(runId: string | null) {
  if (runId && runId !== store.currentRunId) {
    store.currentRunId = runId
    store.selectedSolutionId = null
  }
}

// 选中下拉项后加载该运行，随即重置选择
watch(pastRunSelect, (id) => {
  if (!id) return
  loadPastRun(id)
  pastRunSelect.value = ''
})

const RUN_STATUS_TEXT: Record<RunStatusEnum, string> = {
  PENDING: '排队中',
  RUNNING: '运行中',
  SUCCESS: '已完成',
  FAILURE: '失败',
}

function formatRunTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function runOptionLabel(run: RunResp): string {
  return `${run.name ?? '未命名'} · ${formatRunTime(run.createdAt)} · ${RUN_STATUS_TEXT[run.status]}`
}

// ──── 当前配置预览（只读） ───────────────────────────────────

const configPreview = computed(() => {
  const c = store.config
  const irrPct = c.irr !== undefined ? fmtNumber(c.irr * 100, 1) : '—'
  return `种群 ${c.popSize} · 代数 ${c.maxGen} · 利率 ${irrPct}% · 加速比 ${c.acceleratedRatio} · 最大偏移 ${c.maxOffset}`
})

// ──── 错误信息 ───────────────────────────────────────────────

// 预留：未来可从后端 status 中读取错误详情；目前给通用文案
const errorMessage = '本次优化未成功完成，请检查配置后重试'

// ──── 运行摘要行（替代原 KPI 卡片） ─────────────────────────

const summaryLine = computed(() => {
  const s = store.stats
  const duration = s.bestDuration !== null ? fmtNumber(s.bestDuration, 1) : '—'
  const cost = s.bestCost !== null ? `¥${fmtWanYuan(s.bestCost)} 万` : '—'
  const emission = s.bestEmission !== null ? `${fmtNumber(s.bestEmission / 1000, 2)} t` : '—'
  return `历史优化 ${s.totalRuns} 次 · 最优工期 ${duration} 天 · 最优成本 ${cost} · 最少碳排 ${emission}`
})

// ──── 甘特图：当前运行（常规模式） ──────────────────────────

interface GanttMeta {
  taskId: number
  code: string
  name: string
  mode: TaskMode
}

const selectedSolution = computed(() =>
  store.solutions.find((s) => s.id === store.selectedSolutionId),
)

const ganttItems = computed<GanttChartItem<GanttMeta>[]>(() => {
  if (!selectedSolution.value || store.tasks.length === 0) return []

  const sortedTasks = sortTasksForGantt(store.tasks)
  const strategyMap = new Map(selectedSolution.value.strategies.map((s) => [s.taskId, s]))
  const accRatio = store.status?.acceleratedRatio ?? 0.8

  const items: GanttChartItem<GanttMeta>[] = []
  for (const task of sortedTasks) {
    const strategy = strategyMap.get(task.id)
    if (!strategy) continue

    const isAccelerated = strategy.mode === 1 || strategy.mode === 3
    const duration = isAccelerated ? Math.round(task.duration * accRatio * 10) / 10 : task.duration

    items.push({
      label: task.code ? `${task.code} ${task.name}` : task.name,
      startDay: strategy.start,
      duration,
      color: getStrategyColor(strategy.mode),
      meta: {
        taskId: task.id,
        code: task.code ?? '',
        name: task.name,
        mode: strategy.mode,
      },
    })
  }
  return items
})

const maxDuration = computed<number>(() => {
  let tmp = 0
  for (const item of store.solutions) {
    if (item.duration > tmp) tmp = item.duration
  }
  return tmp
})

function getStrategyColor(mode: TaskMode): string {
  const C = getThemeColors()
  switch (mode) {
    case 0:
      return C.label
    case 1:
      // 加速策略 → 橙（加速专用语义色）
      return C.accel
    case 2:
      // 低碳策略 → 绿（低碳语义色）
      return C.success
    case 3:
      // 加速且低碳 → 紫（双策略色）
      return C.violet
  }
}

function formatGanttTooltip(item: GanttChartItem<GanttMeta>): string {
  const { meta } = item
  if (!meta) return ''
  const modeNames = ['普通', '加速', '低碳', '加速且低碳']
  return `
    <div style="font-size:12px; line-height:1.6;">
      <div style="font-weight:600; margin-bottom:4px;">${meta.code} ${meta.name}</div>
      <div>开始时间：第 ${item.startDay} 天</div>
      <div>结束时间：第 ${item.startDay + item.duration} 天</div>
      <div>工期：${item.duration} 天</div>
      <div>策略：${modeNames[meta.mode]}</div>
    </div>
  `
}

// ──── 甘特图：对比模式（按所选解对应运行的快照回放） ─────────

interface CompareGanttMeta extends GanttMeta {
  source: string
}

const compareGanttItems = computed<GanttChartItem<CompareGanttMeta>[]>(() => {
  const sol = selectedCompareSolution.value
  const snap = snapshot.value
  if (!sol || !snap) return []

  const sortedTasks = sortTasksForGantt(snapshotTasksToTaskResp(snap))
  const strategyMap = new Map(sol.strategies.map((s) => [s.taskId, s]))
  const accRatio = runById.value.get(sol.runId)?.acceleratedRatio ?? 0.8
  const source = runLabel(sol.runId)

  const items: GanttChartItem<CompareGanttMeta>[] = []
  for (const task of sortedTasks) {
    const strategy = strategyMap.get(task.id)
    if (!strategy) continue

    const isAccelerated = strategy.mode === 1 || strategy.mode === 3
    const duration = isAccelerated ? Math.round(task.duration * accRatio * 10) / 10 : task.duration

    items.push({
      label: task.code ? `${task.code} ${task.name}` : task.name,
      startDay: strategy.start,
      duration,
      color: getStrategyColor(strategy.mode),
      meta: {
        taskId: task.id,
        code: task.code ?? '',
        name: task.name,
        mode: strategy.mode,
        source,
      },
    })
  }
  return items
})

const compareMaxDuration = computed<number>(() => {
  let tmp = 0
  for (const sol of rawSolutions.value) {
    if (sol.duration > tmp) tmp = sol.duration
  }
  return tmp
})

function formatCompareGanttTooltip(item: GanttChartItem<CompareGanttMeta>): string {
  const { meta } = item
  if (!meta) return ''
  const modeNames = ['普通', '加速', '低碳', '加速且低碳']
  return `
    <div style="font-size:12px; line-height:1.6;">
      <div style="font-weight:600; margin-bottom:4px;">${meta.code} ${meta.name}</div>
      <div>来源：${meta.source}</div>
      <div>开始时间：第 ${item.startDay} 天</div>
      <div>结束时间：第 ${item.startDay + item.duration} 天</div>
      <div>工期：${item.duration} 天</div>
      <div>策略：${modeNames[meta.mode]}</div>
    </div>
  `
}

// ──── 解集表格：对比模式显示合并幸存解（带来源列） ───────────

const mergedScored = computed(() => scoreSolutions(mergedSolutions.value, store.weights))

const sourceNames = computed<Record<number, string>>(() => {
  const map: Record<number, string> = {}
  for (const sol of mergedSolutions.value) map[sol.id] = runLabel(sol.runId)
  return map
})

/** 表格选中项：对比模式联动散点/甘特，常规模式走当前运行 */
const tableSelectedId = computed<number | null>({
  get: () => (compareActive.value ? compareSelectedSolutionId.value : store.selectedSolutionId),
  set: (id) => {
    if (compareActive.value) compareSelectedSolutionId.value = id
    else store.selectedSolutionId = id
  },
})
</script>

<template>
  <Teleport defer to="#header-actions">
    <button
      v-if="store.isCompleted && store.selectedSolutionId"
      class="btn btn-primary"
      @click="handlePlanEntry"
    >
      <span class="material-symbols-outlined icon-sm">edit_calendar</span>
      编制计划
    </button>
    <button
      v-if="store.isCompleted || store.isFailed"
      class="btn btn-ghost"
      @click="handleResetOptimization"
    >
      <span class="material-symbols-outlined icon-sm">refresh</span>
      重新开始
    </button>

    <RunStatusBar v-else-if="store.currentRunId" :run-id="store.currentRunId" />
  </Teleport>

  <div class="space-y-4">
    <!-- 中央 CTA（运行未完成时显示；完成后让位给图表） -->
    <template v-if="!store.isCompleted">
      <!-- 1. 运行中 -->
      <div v-if="store.hasActiveRun" class="panel emerald p-4">
        <div class="flex-row items-center gap-4 flex">
          <div
            class="w-14 h-14 rounded-2xl flex items-center justify-center bg-primary/20 shrink-0"
          >
            <span class="material-symbols-outlined icon-2xl text-primary progress_activity">
              progress_activity
            </span>
          </div>
          <div class="flex-1 min-w-0 space-y-2">
            <div class="flex items-baseline justify-between gap-4">
              <div>
                <p class="text-base font-semibold text-base-content">优化运行中</p>
                <p class="text-xs text-fg-subtle font-mono mt-0.5">
                  Run ID: {{ store.currentRunId?.slice(0, 8) }}
                </p>
              </div>
              <span class="text-2xl font-bold text-primary tabular-nums">
                {{ store.progress }}%
              </span>
            </div>
            <progress class="progress progress-primary w-full" :value="store.progress" max="100" />
          </div>
          <button
            class="btn btn-ghost btn-sm shrink-0"
            :disabled="!store.currentRunId"
            @click="handleStopOptimization"
          >
            <span class="material-symbols-outlined icon-sm">stop</span>
            停止
          </button>
        </div>
      </div>

      <!-- 2. 失败 -->
      <div v-else-if="store.isFailed" class="panel red p-4">
        <div class="flex-row items-center gap-4 flex">
          <div class="w-14 h-14 rounded-2xl flex items-center justify-center bg-error/15 shrink-0">
            <span class="material-symbols-outlined icon-2xl text-error">error</span>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-base font-semibold text-base-content">优化失败</p>
            <p class="text-sm text-fg-muted mt-1">{{ errorMessage }}</p>
          </div>
          <button class="btn btn-primary shrink-0" @click="handleResetOptimization">
            <span class="material-symbols-outlined icon-sm">refresh</span>
            重新开始
          </button>
        </div>
      </div>

      <!-- 3. 启动中（mutation 进行中，runId 已设置但 status 还未回） -->
      <div v-else-if="store.isLoadingRun" class="panel p-4">
        <div class="flex-row items-center gap-4 flex">
          <span class="loading loading-spinner loading-md text-primary"></span>
          <p class="text-sm text-fg-muted">正在加载运行状态...</p>
        </div>
      </div>

      <!-- 4. idle：中央 CTA + 运行名称 + 配置摘要 -->
      <div v-else class="panel indigo p-4">
        <div class="flex flex-col items-center text-center gap-4">
          <div
            class="w-16 h-16 rounded-2xl flex items-center justify-center bg-primary/15 shrink-0"
          >
            <span class="material-symbols-outlined icon-2xl text-primary">auto_awesome</span>
          </div>
          <div class="space-y-1">
            <h2 class="text-xl font-semibold text-base-content">NSGA-II 多目标优化</h2>
            <p class="text-sm text-fg-muted">
              基于当前资源约束，在工期、成本、碳排放三者之间寻找帕累托最优解
            </p>
          </div>
          <!-- 配置摘要 + 内联参数修改入口 -->
          <div class="w-full text-xs font-mono mt-1" :class="showConfig ? 'max-w-xl' : 'max-w-sm'">
            <div class="flex items-center justify-between gap-3">
              <p class="text-fg-subtle truncate">
                {{ configPreview }}
              </p>
              <button
                type="button"
                class="btn btn-ghost btn-xs gap-1 shrink-0"
                :aria-expanded="showConfig"
                :title="showConfig ? '收起参数' : '修改参数'"
                @click="showConfig = !showConfig"
              >
                <span>修改参数</span>
                <span
                  class="material-symbols-outlined icon-sm transition-transform duration-200"
                  :class="showConfig ? 'rotate-180' : ''"
                  aria-hidden="true"
                >
                  expand_more
                </span>
              </button>
            </div>

            <!-- 内联参数表单（仅存前端 localStorage，启动优化时生效） -->
            <div
              v-if="showConfig"
              class="border-t border-base-content/10 pt-4 mt-3 text-left font-sans"
            >
              <OptimizationConfig
                :config="store.config"
                @update:config="store.updateConfig($event)"
              />
            </div>
          </div>

          <div class="fieldset w-full max-w-sm text-left">
            <label class="fieldset-label" for="run-name">
              运行名称 <span class="text-error" aria-hidden="true">*</span>
            </label>
            <input
              id="run-name"
              v-model="runName"
              class="input w-full"
              :class="{ 'input-error': runNameTouched && !runName.trim() }"
              placeholder="例如：串行施工方案 #1"
              type="text"
              @blur="runNameTouched = true"
              @keydown.enter="handleStartOptimization"
            />
            <span v-if="runNameTouched && !runName.trim()" class="mt-1 text-xs text-error">
              请输入本次运行的名称（用于历史记录与运行对比辨认）
            </span>
          </div>

          <button
            class="btn btn-primary btn-lg gap-2 mt-1"
            :disabled="!runName.trim()"
            @click="handleStartOptimization"
          >
            <span class="material-symbols-outlined">play_arrow</span>
            开始优化
          </button>

          <!-- 数据体检被动入口：仅存在零碳因子警告时出现 -->
          <RouterLink
            v-if="diagZeroFactorCount > 0"
            :to="`/project/${currentProjectId}/settings/diagnostics`"
            class="link link-warning text-xs gap-1 inline-flex items-center mt-2"
          >
            <span class="material-symbols-outlined icon-sm">health_and_safety</span>
            数据体检：{{ diagZeroFactorCount }} 项零碳因子注意
          </RouterLink>

          <!-- 历史运行：查看过去的优化结果（仅已完成运行） -->
          <div
            v-if="successRuns.length > 0"
            class="w-full max-w-sm border-t border-base-content/10 pt-4"
          >
            <div class="flex items-center gap-2">
              <span class="text-sm text-fg-muted shrink-0">或查看历史运行</span>
              <select
                v-model="pastRunSelect"
                class="select select-sm flex-1"
                aria-label="选择历史运行"
              >
                <option :value="''" disabled>选择历史运行</option>
                <option v-for="run in successRuns" :key="run.id" :value="run.id">
                  {{ runOptionLabel(run) }}
                </option>
              </select>
              <button
                class="btn btn-ghost btn-sm shrink-0"
                :disabled="!latestSuccessRunId"
                @click="loadPastRun(latestSuccessRunId)"
              >
                最近一次优化
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 完成后：单一 panel + 发丝线分割（运行对比 / 图表 / 解集表格） -->
    <template v-else>
      <div class="panel panel-grid grid-cols-12 overflow-hidden">
        <!-- ① 运行对比选择器 -->
        <section
          class="p-4 col-span-12"
          :class="compareActive ? 'xl:col-span-7' : 'xl:col-span-12'"
        >
          <div class="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h2 class="section-title">运行对比</h2>
              <p class="text-xs text-fg-muted">
                勾选两个已完成运行，自动合并解集并在图表中叠加对比
              </p>
            </div>
            <p class="text-xs font-mono text-fg-subtle text-right font-num">
              {{ summaryLine }}
            </p>
          </div>

          <div class="mt-3">
            <CompareRunsPanel />
          </div>
        </section>

        <!-- ④ 对比统计（仅对比时，与选择器同排） -->
        <section v-if="compareActive" class="p-4 col-span-12 xl:col-span-5">
          <CompareStatsPanel />
        </section>

        <!-- ② 散点图 -->
        <section class="p-4 col-span-12 xl:col-span-7">
          <CompareParetoChart
            v-if="compareActive"
            v-model:selected-id="compareSelectedSolutionId"
            :groups="groups"
            :dominated-ids="dominatedIds"
            :has-merged="hasMerged"
          />
          <ParetoChart
            v-else
            v-model:selected-id="store.selectedSolutionId"
            :solutions="store.solutions"
          />
        </section>

        <section class="p-4 col-span-12 xl:col-span-5">
          <h2 class="section-title">甘特图</h2>

          <template v-if="compareActive">
            <p v-if="selectedCompareSolution" class="text-xs text-fg-muted mb-3 font-mono">
              方案 #{{ selectedCompareSolution.id }} · 来源：{{
                runLabel(selectedCompareSolution.runId)
              }}
            </p>
            <div v-if="isLoadingSnapshot" class="space-y-3">
              <div v-for="i in 4" :key="i" class="skeleton h-10 w-full rounded-lg"></div>
            </div>
            <GanttChart
              v-else-if="compareGanttItems.length > 0"
              :items="compareGanttItems"
              :total-days="compareMaxDuration"
              :tooltip-formatter="
                formatCompareGanttTooltip as (item: GanttChartItem<unknown>) => string
              "
            />
            <ChartEmptyState
              v-else
              icon="schedule"
              title="暂无甘特图"
              description="在散点图中点选一个方案查看甘特图"
            />
          </template>

          <template v-else>
            <p v-if="selectedSolution" class="text-xs text-fg-muted mb-3 font-mono">
              方案 #{{ selectedSolution.id }} · 当前运行
            </p>
            <GanttChart
              v-if="ganttItems.length > 0"
              :items="ganttItems"
              :total-days="maxDuration"
              :tooltip-formatter="formatGanttTooltip as (item: GanttChartItem<unknown>) => string"
            />
            <ChartEmptyState
              v-else
              icon="schedule"
              title="暂无甘特图"
              description="在散点图中点选一个方案查看甘特图"
            />
          </template>
        </section>

        <!-- ⑤ 解集表格（限高，内部滚动） -->
        <section class="p-4 col-span-12">
          <div class="h-96">
            <ParetoSolutionsTable
              v-model:selected-id="tableSelectedId"
              v-model:weights="store.weights"
              :solutions="compareActive ? mergedScored : store.rankedSolutions"
              :loading="compareActive ? isMerging || !hasMerged : store.isLoadingSolutions"
              :source-names="compareActive ? sourceNames : undefined"
              :presets="WEIGHT_PRESETS"
              :custom-presets="store.customPresets"
              :tasks="store.tasks"
              @add-preset="handleAddPreset"
              @remove-preset="handleRemovePreset"
            />
          </div>
        </section>
      </div>
    </template>
  </div>

  <!-- 保存预设弹窗 -->
  <SaveWeightPresetModal
    v-model:open="showSavePreset"
    :weights="store.weights"
    :external-error="presetExternalError"
    @confirm="confirmAddPreset"
  />
</template>
