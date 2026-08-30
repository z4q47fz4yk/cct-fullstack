/**
 * 优化洞察状态管理
 *
 * 状态流转：
 * IDLE (currentRunId=null)
 *   → startOptimization()
 *   → RUNNING (currentRunId≠null, status=PENDING/RUNNING)
 *   → COMPLETED (status=SUCCESS) / FAILED (status=FAILURE)
 *   → resetOptimization() → IDLE
 *
 * Query 生命周期：
 * - 状态查询：RUNNING 阶段启用 + autoRefetch 轮询
 * - 解集查询：COMPLETED 阶段启用
 * - 历史记录：常驻，mutation 后刷新
 */
import { computed, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryCache } from '@pinia/colada'
import { useProjectStorage } from '@/composables/useProjectStorage'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import {
  listOptimizeRecordsQuery,
  listOptimizeRecordResultQuery,
  getOptimizeRecordStatusQuery,
  createOptimizeRecordMutation,
  breakOptimizeMutation,
  listTasksQuery,
} from '@/client/@pinia/colada.gen'
import type { RunConfig } from '@/client/types.gen'
import { defineStore } from 'pinia'
import { notifyInfo } from '@/composables/useToast'
import {
  DEFAULT_PARETO_WEIGHTS,
  type NamedWeightPreset,
  type ParetoWeights,
} from '@/types/paretoWeights'
import { scoreSolutions, type ScoredSolution } from '@/utils/paretoScore'

// ========== 默认配置 ==========
// 优化发生在计划阶段：usageType 默认 PLANNED（计划用量口径），与后端默认一致
const DEFAULT_CONFIG: RunConfig = {
  popSize: 50,
  maxGen: 100,
  irr: 0.05,
  acceleratedRatio: 0.8,
  maxOffset: 3,
  usageType: 'PLANNED',
}

// ========== Store ==========
export const useInsightsStore = defineStore('insights', () => {
  const queryCache = useQueryCache()
  const { currentProjectId, isInProject } = useProjectContext()

  // ========== 持久化状态 ==========
  const currentRunId = useProjectStorage<string | null>('insights:currentRunId', null)
  const config = useProjectStorage<RunConfig>('insights:config', { ...DEFAULT_CONFIG })
  const weights = useProjectStorage<ParetoWeights>('insights:pareto-weights', {
    ...DEFAULT_PARETO_WEIGHTS,
  })
  const customPresets = useProjectStorage<NamedWeightPreset[]>('insights:custom-weight-presets', [])

  // ========== 临时状态 ==========
  const selectedSolutionId = ref<number | null>(null)

  // ========== Query: 运行状态 ==========
  const statusQuery = useQuery(() => ({
    ...getOptimizeRecordStatusQuery({
      path: { project_id: currentProjectId.value!, id: currentRunId.value ?? '' },
    }),
    enabled: isInProject.value && !!currentRunId.value,
    staleTime: 1000,
    autoRefetch: (state: { data?: { status?: string } | null }) => {
      const status = state.data?.status
      return status === 'RUNNING' || status === 'PENDING' ? 1000 : false
    },
  }))

  const currentRunStatus = computed(() => statusQuery.data.value?.status ?? null)
  const isRunning = computed(
    () => currentRunStatus.value === 'RUNNING' || currentRunStatus.value === 'PENDING',
  )
  const isCompleted = computed(() => currentRunStatus.value === 'SUCCESS')
  const isFailed = computed(() => currentRunStatus.value === 'FAILURE')
  const hasActiveRun = computed(() => !!currentRunId.value && !isCompleted.value && !isFailed.value)

  const progress = computed(() => {
    const data = statusQuery.data.value
    if (!data) return 0
    const { currGen, maxGen } = data
    if (maxGen === 0) return 0
    return Math.min(Math.round((currGen / maxGen) * 100), 100)
  })

  const isLoadingRun = computed(() => statusQuery.isLoading.value && !!currentRunId.value)

  /** currentRunId 存在但后端查询已完成且无有效状态（不存在 / 中断 / 未知） */
  const isStaleRun = computed(() => {
    if (!currentRunId.value) return false
    if (statusQuery.error.value) return true
    if (!statusQuery.isLoading.value && currentRunStatus.value === null) return true
    return false
  })

  // ========== Query: 解集列表 ==========
  const solutionsQuery = useQuery(() => ({
    ...listOptimizeRecordResultQuery({
      path: { project_id: currentProjectId.value!, id: currentRunId.value ?? '' },
      query: {
        page: 1,
        per_page: FETCH_ALL_PAGE_SIZE,
      },
    }),
    enabled: isInProject.value && isCompleted.value,
  }))

  const solutions = computed(() => solutionsQuery.data.value?.items ?? [])
  const isLoadingSolutions = computed(() => solutionsQuery.isLoading.value)

  // ========== Query: 历史记录 ==========
  const recordsQuery = useQuery(() => ({
    ...listOptimizeRecordsQuery({
      path: { project_id: currentProjectId.value! },
      query: { per_page: FETCH_ALL_PAGE_SIZE },
    }),
    enabled: isInProject.value,
  }))

  const totalRuns = computed(() => recordsQuery.data.value?.total ?? 0)
  const records = computed(() => recordsQuery.data.value?.items ?? [])
  const isLoadingRecords = computed(() => recordsQuery.isLoading.value)

  // ========== Query: 任务列表（用于甘特图） ==========
  const tasksQuery = useQuery(() => ({
    ...listTasksQuery({
      path: { project_id: currentProjectId.value! },
      query: { per_page: FETCH_ALL_PAGE_SIZE },
    }),
    enabled: isInProject.value,
  }))

  const tasks = computed(() => {
    const tmp = tasksQuery.state.value?.data?.items ?? []
    if (tmp.length >= 1000) {
      console.warn('len(tasks) > 1000. Make sure all tasks are here')
    }
    return tmp
  })

  // ========== 统计 ==========
  const stats = computed(() => ({
    totalRuns: totalRuns.value,
    bestDuration:
      solutions.value.length > 0 ? Math.min(...solutions.value.map((s) => s.duration)) : null,
    bestCost: solutions.value.length > 0 ? Math.min(...solutions.value.map((s) => s.cost)) : null,
    bestEmission:
      solutions.value.length > 0 ? Math.min(...solutions.value.map((s) => s.emission)) : null,
  }))

  // ========== 加权排序后的解集 ==========
  const rankedSolutions = computed<ScoredSolution[]>(() =>
    solutions.value.length > 0 ? scoreSolutions(solutions.value, weights.value) : [],
  )

  // ========== Mutation: 启动优化 ==========
  const startMutation = useMutation(createOptimizeRecordMutation())

  async function startOptimization(name?: string | null) {
    if (startMutation.isLoading.value) return
    try {
      const resp = await startMutation.mutateAsync({
        path: { project_id: currentProjectId.value! },
        body: { ...config.value, name: name?.trim() || null },
      })
      const runId = resp?.runId
      if (runId) {
        currentRunId.value = runId
        notifyInfo({ title: '优化任务已启动', description: '将在后台运行，完成后自动展示结果' })
      }
    } catch (e) {
      console.error('Start optimization failed:', e)
      throw e
    }
  }

  // ========== Mutation: 停止优化 ==========
  const stopMutation = useMutation(breakOptimizeMutation())

  async function stopOptimization() {
    if (!currentRunId.value) return
    try {
      await stopMutation.mutateAsync({
        path: { project_id: currentProjectId.value!, id: currentRunId.value },
      })
      await queryCache.invalidateQueries({
        key: getOptimizeRecordStatusQuery({
          path: { project_id: currentProjectId.value!, id: currentRunId.value },
        }).key,
      })
      notifyInfo({ title: '已发送停止指令' })
    } catch (e) {
      console.error('Stop optimization failed:', e)
    }
  }

  // ========== Actions ==========
  function resetOptimization() {
    currentRunId.value = null
    selectedSolutionId.value = null
  }

  // 检测到 stale run 时自动清除，防止页面卡在「优化运行中」
  watch(isStaleRun, (stale) => {
    if (stale) {
      notifyInfo({ title: '优化记录已失效', description: '已自动清除过期的运行记录' })
      resetOptimization()
    }
  })

  function updateConfig(partial: Partial<RunConfig>) {
    config.value = { ...config.value, ...partial }
  }

  function selectSolution(id: number | null) {
    selectedSolutionId.value = id
  }

  // ========== 权重预设：增删 ==========

  /**
   * 把给定权重另存为命名预设。
   * @returns true=成功；false=同名冲突
   */
  function addCustomPreset(name: string, values: ParetoWeights): boolean {
    const trimmed = name.trim()
    if (!trimmed) return false
    if (customPresets.value.some((p) => p.label === trimmed)) return false
    customPresets.value = [
      ...customPresets.value,
      {
        id: crypto.randomUUID(),
        label: trimmed,
        values: { ...values },
      },
    ]
    return true
  }

  function removeCustomPreset(id: string) {
    customPresets.value = customPresets.value.filter((p) => p.id !== id)
  }

  return {
    // State
    currentRunId,
    selectedSolutionId,
    config,
    weights,
    customPresets,
    tasks,

    // Query state
    solutions,
    rankedSolutions,
    isLoadingSolutions,
    currentRunStatus,
    isLoadingRun,
    totalRuns,
    records,
    isLoadingRecords,
    progress,
    stats,
    status: statusQuery.data,

    // Derived state
    isRunning,
    isCompleted,
    isFailed,
    hasActiveRun,

    // Actions
    updateConfig,
    selectSolution,
    startOptimization,
    stopOptimization,
    resetOptimization,
    addCustomPreset,
    removeCustomPreset,
  }
})
