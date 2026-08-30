/**
 * 工序按日进度 API 封装
 *
 * append-only：每次录入新增一行，汇总取 (date, createdAt, id) 最后一条；
 * 100% 即完成，实际完成日期随最新状态变化。
 */
import { computed } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type { TaskProgressBatchItem } from '@/client/types.gen'
import {
  createProgressMutation,
  batchCreateProgressMutation,
  listProgressQuery,
  taskProgressSummaryQuery,
  projectProgressSummariesQuery,
  projectProgressSummariesQueryKey,
} from '@/client/@pinia/colada.gen'

export function useProgressApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  // ──── 项目汇总（全部工序） ───────────────────────────────
  const projectSummariesQuery = useQuery(() => ({
    ...projectProgressSummariesQuery({ path: { project_id: currentProjectId.value! } }),
    enabled: !!currentProjectId.value,
  }))

  const projectSummaries = computed(() => projectSummariesQuery.state.value?.data ?? [])
  const isLoadingProjectSummaries = computed(
    () => projectSummariesQuery.asyncStatus.value === 'loading',
  )

  async function invalidateAll() {
    await queryCache.invalidateQueries({
      key: projectProgressSummariesQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  }

  // ──── 单工序录入 / 日报批量 ──────────────────────────────
  const createMutation = useMutation({
    ...createProgressMutation(),
    onSuccess: invalidateAll,
  })
  const batchMutation = useMutation({
    ...batchCreateProgressMutation(),
    onSuccess: invalidateAll,
  })

  async function recordProgress(taskId: number, date: string, percent: number) {
    return createMutation.mutateAsync({
      path: { project_id: currentProjectId.value!, task_id: taskId },
      body: { date, percent },
    })
  }

  async function recordProgressBatch(items: TaskProgressBatchItem[]) {
    return batchMutation.mutateAsync({
      path: { project_id: currentProjectId.value! },
      body: { items },
    })
  }

  return {
    projectSummaries,
    isLoadingProjectSummaries,
    recordProgress,
    recordProgressBatch,
    isRecording: createMutation.isLoading.value || batchMutation.isLoading.value,
    refresh: projectSummariesQuery.refresh,
  }
}

export type { TaskProgressBatchItem }

/** 单工序历史 / 汇总查询（按需使用，避免每个页面都拉全量） */
export function useTaskProgress(taskId: () => number | null) {
  const { currentProjectId } = useProjectContext()
  const tid = computed(() => taskId())

  const historyQuery = useQuery(() => ({
    ...listProgressQuery({
      path: { project_id: currentProjectId.value!, task_id: tid.value! },
    }),
    enabled: !!currentProjectId.value && tid.value !== null,
  }))

  const summaryQuery = useQuery(() => ({
    ...taskProgressSummaryQuery({
      path: { project_id: currentProjectId.value!, task_id: tid.value! },
    }),
    enabled: !!currentProjectId.value && tid.value !== null,
  }))

  return {
    history: computed(() => historyQuery.state.value?.data?.items ?? []),
    summary: computed(() => summaryQuery.state.value?.data ?? null),
    isLoading: computed(
      () =>
        historyQuery.asyncStatus.value === 'loading' ||
        summaryQuery.asyncStatus.value === 'loading',
    ),
    refresh: () => Promise.all([historyQuery.refresh(), summaryQuery.refresh()]),
  }
}
