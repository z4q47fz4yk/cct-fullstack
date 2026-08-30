/**
 * 串行/并行施工对比（useParetoCompare）
 *
 * 职责：
 * - 从历史运行中选择两个 SUCCESS 运行（用 name 标签辨认，可事后改名）
 * - 分别拉取两个运行的原始解集，调用后端 merge 端点计算跨运行支配关系；
 *   选满两个运行后自动触发合并，无需手动点击
 * - 被支配/重复解 = 原始解集 id 并集 − 合并幸存集 id，前端标记半透明
 * - 点选解时按该运行自己的任务/依赖快照回放甘特图
 *
 * 对比公平性前提：两次运行间的资源用量、单价、碳因子、资源约束未变化
 *（串行/并行施工用例下成立），页面需给出提示。
 *
 * 说明：选择状态为模块级单例（session 级），页面与面板组件共享同一实例；
 * 查询/变更由各调用方在自身 setup 中创建，键去重后共享缓存。
 */
import { computed, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { useInsightsStore } from '@/stores/insights'
import {
  deleteOptimizeMutation,
  getOptimizeRunSnapshotQuery,
  listOptimizeRecordResultQuery,
  listOptimizeRecordsQuery,
  mergeOptimizeSolutionsMutation,
  updateOptimizeRecordMutation,
} from '@/client/@pinia/colada.gen'
import type {
  OptimizeSolution,
  RunResp,
  RunTaskSnapshotResp,
  TaskWithTagsResp,
} from '@/client/types.gen'
import { formatHttpError } from '@/utils/error'
import { notifyError, notifySuccess } from '@/composables/useToast'

export interface CompareRunGroup {
  runId: string
  label: string
  color: 'indigo' | 'cyan'
  solutions: OptimizeSolution[]
}

export interface RunCompareStats {
  runId: string
  label: string
  total: number
  survivor: number
  dominated: number
  bestDuration: number | null
  bestCost: number | null
  bestEmission: number | null
}

/** 将快照任务合成为 TaskWithTagsResp 形状（isCritical 恒 false），复用 sortTasksForGantt 的拓扑排序。
 *  依赖统一按 FS 合成：甘特排序只使用边的方向（taskId/predecessorId），type 不影响渲染。 */
export function snapshotTasksToTaskResp(snapshot: RunTaskSnapshotResp): TaskWithTagsResp[] {
  return snapshot.tasks.map((t) => ({
    id: t.id,
    code: t.code,
    name: t.name,
    duration: t.duration,
    description: '',
    completed: 0,
    isCritical: false,
    createdAt: '',
    updatedAt: '',
    predecessors: snapshot.dependencies
      .filter((d) => d.taskId === t.id)
      .map((d) => ({ id: d.predecessorId, code: '', name: '', type: 'FS' as const })),
  }))
}

/** 任务快照的结构指纹：任务排序后拼接。可对比性只看任务集是否一致，依赖差异正是对比的意义所在 */
function snapshotFingerprint(snap: RunTaskSnapshotResp): string {
  return [...snap.tasks]
    .sort((a, b) => a.id - b.id)
    .map((t) => `${t.id}:${t.code}:${t.name}:${t.duration}`)
    .join('|')
}

/** 两次运行的任务集一致（id/code/name/duration 全等）才可对比；依赖可不同 */
export function snapshotsCompatible(a: RunTaskSnapshotResp, b: RunTaskSnapshotResp): boolean {
  return snapshotFingerprint(a) === snapshotFingerprint(b)
}

// ========== 模块级单例状态（session 级） ==========
const compareRunIds = ref<string[]>([])
const compareSelectedSolutionId = ref<number | null>(null)
const mergedSolutions = ref<OptimizeSolution[]>([])

/** 基线 pin 后的快照可对比性校验状态 */
const isCheckingSnapshots = ref(false)
const snapshotsReady = ref(false)
const incompatibleRunIds = ref<Set<string>>(new Set())
let snapshotCheckToken = 0
/** 已校验的基线 id：同一基线不重复拉取快照 */
let lastBaselineChecked: string | null = null

const RUN_COLORS: Record<number, 'indigo' | 'cyan'> = { 0: 'indigo', 1: 'cyan' }

/**
 * 跨实例共享的合并中标记：多个 useParetoCompare 实例各自注册自动合并 watch，
 * 该标记在首个 await 前同步置位，同一次 flush 中后到的实例直接返回，
 * 避免并发重复合并与重复 toast。
 */
let mergeInFlight = false

export function useParetoCompare() {
  const queryCache = useQueryCache()
  const { currentProjectId, isInProject } = useProjectContext()
  const store = useInsightsStore()

  // ========== 运行元数据 ==========
  const runById = computed(() => {
    const map = new Map<string, RunResp>()
    for (const r of store.records) map.set(r.id, r)
    return map
  })

  function runLabel(runId: string): string {
    return runById.value.get(runId)?.name ?? '未命名'
  }

  function isSuccessRun(runId: string): boolean {
    return runById.value.get(runId)?.status === 'SUCCESS'
  }

  /** 点击 pin：设定基线（移至第一个）；已是基线则取消 */
  function setBaseline(runId: string) {
    compareRunIds.value = compareRunIds.value[0] === runId ? [] : [runId]
  }

  /** 有基线时点击任意解集：与该基线对比（替换第二个，触发重新合并） */
  function compareWith(runId: string) {
    const baseline = compareRunIds.value[0]
    if (baseline && baseline !== runId) {
      compareRunIds.value = [baseline, runId]
    }
  }

  function clearCompareRuns() {
    compareRunIds.value = []
    compareSelectedSolutionId.value = null
    mergedSolutions.value = []
  }

  // ========== 快照可对比性 ==========

  function clearCompatibility() {
    snapshotCheckToken++
    lastBaselineChecked = null
    isCheckingSnapshots.value = false
    snapshotsReady.value = false
    incompatibleRunIds.value = new Set()
  }

  /** 基线 pin 后拉取全部 SUCCESS 运行的任务/依赖快照，标记与基线不一致的运行 */
  async function checkSnapshotCompatibility() {
    const baselineId = compareRunIds.value[0]
    if (!baselineId) {
      clearCompatibility()
      return
    }
    if (lastBaselineChecked === baselineId) return
    isCheckingSnapshots.value = true
    const token = ++snapshotCheckToken
    try {
      const successIds = store.records.filter((r) => r.status === 'SUCCESS').map((r) => r.id)
      await Promise.all(
        successIds.map(async (id) => {
          const entry = queryCache.ensure(
            getOptimizeRunSnapshotQuery({
              path: { project_id: currentProjectId.value!, id },
            }),
          )
          await queryCache.fetch(entry)
        }),
      )
      if (token !== snapshotCheckToken) return
      const snapshots = new Map<string, RunTaskSnapshotResp>()
      for (const id of successIds) {
        const opts = getOptimizeRunSnapshotQuery({
          path: { project_id: currentProjectId.value!, id },
        })
        const data = queryCache.getQueryData<RunTaskSnapshotResp>(opts.key)
        if (data) snapshots.set(id, data)
      }
      const baseline = snapshots.get(baselineId)
      const incompatible = new Set<string>()
      if (baseline) {
        for (const [id, snap] of snapshots) {
          if (id !== baselineId && !snapshotsCompatible(baseline, snap)) incompatible.add(id)
        }
      }
      incompatibleRunIds.value = incompatible
      snapshotsReady.value = true
      lastBaselineChecked = baselineId
    } catch (e) {
      console.error('Check snapshot compatibility failed:', e)
      // 校验失败降级：视为全兼容
      incompatibleRunIds.value = new Set()
      snapshotsReady.value = true
    } finally {
      if (token === snapshotCheckToken) isCheckingSnapshots.value = false
    }
  }

  // 运行选择变化后：清旧结果；无基线时清理校验；基线 pin 后校验可对比性；选满两个自动合并
  watch(compareRunIds, async () => {
    compareSelectedSolutionId.value = null
    mergedSolutions.value = []
    if (compareRunIds.value.length === 0) {
      clearCompatibility()
      return
    }
    void checkSnapshotCompatibility()
    if (compareRunIds.value.length === 2 && compareRunIds.value.every((id) => isSuccessRun(id))) {
      await runMerge()
    }
  })

  // 切换项目后清除选择，避免跨项目残留 run id
  watch(currentProjectId, () => {
    clearCompareRuns()
  })

  const canCompare = computed(
    () => compareRunIds.value.length === 2 && compareRunIds.value.every((id) => isSuccessRun(id)),
  )

  // ========== 每运行原始解集（固定两个查询槽位） ==========
  const resultQuery0 = useQuery(() => {
    const runId = compareRunIds.value[0]
    return {
      ...listOptimizeRecordResultQuery({
        path: { project_id: currentProjectId.value!, id: runId ?? '' },
        query: { page: 1, per_page: FETCH_ALL_PAGE_SIZE },
      }),
      enabled: isInProject.value && !!runId && isSuccessRun(runId),
    }
  })

  const resultQuery1 = useQuery(() => {
    const runId = compareRunIds.value[1]
    return {
      ...listOptimizeRecordResultQuery({
        path: { project_id: currentProjectId.value!, id: runId ?? '' },
        query: { page: 1, per_page: FETCH_ALL_PAGE_SIZE },
      }),
      enabled: isInProject.value && !!runId && isSuccessRun(runId),
    }
  })

  const rawSolutions = computed<OptimizeSolution[]>(() => [
    ...(resultQuery0.data.value?.items ?? []),
    ...(resultQuery1.data.value?.items ?? []),
  ])

  /** 按 runId 分组的原始解集（含被支配解），供图表叠加渲染 */
  const groups = computed<CompareRunGroup[]>(() =>
    compareRunIds.value.map((runId, idx) => ({
      runId,
      label: runLabel(runId),
      color: RUN_COLORS[idx] ?? 'indigo',
      solutions: rawSolutions.value.filter((s) => s.runId === runId),
    })),
  )

  // ========== Mutation: 合并（服务端计算支配关系） ==========
  const mergeMutation = useMutation(mergeOptimizeSolutionsMutation())

  async function runMerge() {
    if (!canCompare.value || mergeInFlight || mergeMutation.isLoading.value) return
    const pair = [...compareRunIds.value]
    mergeInFlight = true
    try {
      const resp = await mergeMutation.mutateAsync({
        path: { project_id: currentProjectId.value! },
        body: { runIds: pair },
      })
      // 合并期间对比对象已变化：结果作废，由 finally 重跑最新对
      if (pair.join() !== compareRunIds.value.join()) return
      mergedSolutions.value = resp?.items ?? []
      notifySuccess({
        title: '已自动合并',
        description: `两个运行共保留 ${mergedSolutions.value.length} 个非支配解`,
      })
    } catch (e) {
      if (pair.join() !== compareRunIds.value.join()) return
      console.error('Merge optimize solutions failed:', e)
      notifyError({ title: '合并失败', description: formatHttpError(e, '无法合并两个运行') })
    } finally {
      mergeInFlight = false
      if (compareRunIds.value.length === 2 && pair.join() !== compareRunIds.value.join()) {
        void runMerge()
      }
    }
  }

  const isMerging = computed(() => mergeMutation.isLoading.value)
  const hasMerged = computed(() => mergedSolutions.value.length > 0)

  /** 被支配或目标值重复的解 id（原始并集 − 合并幸存集） */
  const dominatedIds = computed(() => {
    const survivor = new Set(mergedSolutions.value.map((s) => s.id))
    return new Set(rawSolutions.value.filter((s) => !survivor.has(s.id)).map((s) => s.id))
  })

  // ========== 统计 ==========
  const statsByRun = computed<RunCompareStats[]>(() =>
    groups.value.map((g) => {
      const raw = g.solutions
      const survivor = mergedSolutions.value.filter((s) => s.runId === g.runId).length
      const min = (sel: (s: OptimizeSolution) => number) =>
        raw.length > 0 ? Math.min(...raw.map(sel)) : null
      return {
        runId: g.runId,
        label: g.label,
        total: raw.length,
        survivor,
        dominated: raw.length - survivor,
        bestDuration: min((s) => s.duration),
        bestCost: min((s) => s.cost),
        bestEmission: min((s) => s.emission),
      }
    }),
  )

  // ========== Mutation: 改名（后端持久化，任意状态可改） ==========
  const renameMutation = useMutation(updateOptimizeRecordMutation())

  async function renameRun(runId: string, name: string | null) {
    try {
      await renameMutation.mutateAsync({
        path: { project_id: currentProjectId.value!, id: runId },
        body: { name },
      })
      await queryCache.invalidateQueries({
        key: listOptimizeRecordsQuery({ path: { project_id: currentProjectId.value! } }).key,
      })
      notifySuccess({ title: '运行标签已更新' })
    } catch (e) {
      console.error('Rename optimize run failed:', e)
      notifyError({ title: '改名失败', description: formatHttpError(e) })
    }
  }

  // ========== Mutation: 删除运行记录 ==========
  const deleteMutation = useMutation(deleteOptimizeMutation())

  async function deleteRun(runId: string) {
    try {
      await deleteMutation.mutateAsync({
        path: { project_id: currentProjectId.value!, id: runId },
      })
      // 清理残留状态：从对比选择中移除；若删除的是当前查看的运行则回到空闲态
      if (compareRunIds.value.includes(runId)) {
        compareRunIds.value = compareRunIds.value.filter((x) => x !== runId)
      }
      if (store.currentRunId === runId) {
        store.currentRunId = null
        store.selectedSolutionId = null
      }
      await queryCache.invalidateQueries({
        key: listOptimizeRecordsQuery({ path: { project_id: currentProjectId.value! } }).key,
      })
      notifySuccess({ title: '运行记录已删除' })
    } catch (e) {
      console.error('Delete optimize run failed:', e)
      notifyError({ title: '删除失败', description: formatHttpError(e) })
    }
  }

  // ========== 甘特图回放（按运行自己的快照） ==========
  const selectedCompareSolution = computed<OptimizeSolution | null>(
    () => rawSolutions.value.find((s) => s.id === compareSelectedSolutionId.value) ?? null,
  )

  const snapshotQuery = useQuery(() => ({
    ...getOptimizeRunSnapshotQuery({
      path: {
        project_id: currentProjectId.value!,
        id: selectedCompareSolution.value?.runId ?? '',
      },
    }),
    enabled: isInProject.value && !!selectedCompareSolution.value,
  }))

  const snapshot = computed<RunTaskSnapshotResp | null>(() => snapshotQuery.data.value ?? null)
  const isLoadingSnapshot = computed(() => snapshotQuery.isLoading.value)

  return {
    // 选择状态
    compareRunIds,
    compareSelectedSolutionId,
    canCompare,
    setBaseline,
    compareWith,
    clearCompareRuns,
    // 快照可对比性
    isCheckingSnapshots,
    snapshotsReady,
    incompatibleRunIds,
    checkSnapshotCompatibility,
    clearCompatibility,
    // 数据
    groups,
    rawSolutions,
    mergedSolutions,
    dominatedIds,
    isMerging,
    hasMerged,
    statsByRun,
    // 操作
    runMerge,
    runLabel,
    renameRun,
    deleteRun,
    // 运行元数据
    runById,
    // 甘特回放
    selectedCompareSolution,
    snapshot,
    isLoadingSnapshot,
  }
}
