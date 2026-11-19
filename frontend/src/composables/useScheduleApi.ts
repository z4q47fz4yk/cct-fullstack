import { computed, type Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import {
  listTasksQuery,
  listTasksQueryKey,
  getScheduleStatsQuery,
  getScheduleStatsQueryKey,
  createTaskMutation,
  updateTaskMutation,
  deleteTaskMutation,
  addTaskPredecessorMutation,
  removeTaskPredecessorMutation,
  updateTaskPredecessorMutation,
  getAvailablePredecessorsQuery,
  getAvailablePredecessorsQueryKey,
} from '@/client/@pinia/colada.gen'

/**
 * 进度管理 API 封装
 * 分离 API 调用逻辑与 UI 逻辑
 */
export function useScheduleApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  // 统一的缓存刷新函数
  const invalidateTasksCache = async () => {
    await queryCache.invalidateQueries({
      key: listTasksQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  }

  const invalidateStatsCache = async () => {
    await queryCache.invalidateQueries({
      key: getScheduleStatsQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  }

  // 前置依赖变更：任务列表 + 该任务的可选前置任务 + 统计（关键路径）全部失效
  const invalidatePredecessorCaches = async (vars?: { path: { id: number } }) => {
    const projectId = currentProjectId.value!
    const invalidations = [
      queryCache.invalidateQueries({ key: listTasksQueryKey({ path: { project_id: projectId } }) }),
      queryCache.invalidateQueries({
        key: getScheduleStatsQueryKey({ path: { project_id: projectId } }),
      }),
    ]
    if (vars?.path.id != null) {
      invalidations.push(
        queryCache.invalidateQueries({
          key: getAvailablePredecessorsQueryKey({
            path: { project_id: projectId, id: vars.path.id },
          }),
        }),
      )
    }
    await Promise.all(invalidations)
  }

  // 查询任务列表（include_tags 附带直接挂载的标签，供表格标签列展示）；
  // 一次拉全量后由页面本地筛选（任务名称搜索不走服务端参数，保证实时、大小写不敏感）
  const {
    state: tasksState,
    asyncStatus: tasksAsyncStatus,
    error: tasksError,
    refresh: refreshTasks,
  } = useQuery(() =>
    listTasksQuery({
      path: { project_id: currentProjectId.value! },
      query: {
        include_tags: true,
        per_page: FETCH_ALL_PAGE_SIZE,
      },
    }),
  )

  const tasks = computed(() => tasksState.value?.data?.items ?? [])
  const isLoadingTasks = computed(() => tasksAsyncStatus.value === 'loading')

  // 查询统计信息
  const {
    state: statsState,
    asyncStatus: statsAsyncStatus,
    error: statsError,
    refresh: refreshStats,
  } = useQuery(() =>
    getScheduleStatsQuery({
      path: { project_id: currentProjectId.value! },
    }),
  )

  const stats = computed(() => statsState.value?.data ?? null)
  const isLoadingStats = computed(() => statsAsyncStatus.value === 'loading')

  // 创建任务
  const { mutateAsync: createTask, asyncStatus: createStatus } = useMutation({
    ...createTaskMutation(),
    onSuccess: async () => {
      await invalidateTasksCache()
      await invalidateStatsCache()
    },
  })

  // 更新任务
  const { mutateAsync: updateTask, asyncStatus: updateStatus } = useMutation({
    ...updateTaskMutation(),
    onSuccess: async () => {
      await invalidateTasksCache()
      await invalidateStatsCache()
    },
  })

  // 删除任务
  const { mutateAsync: deleteTask, asyncStatus: deleteStatus } = useMutation({
    ...deleteTaskMutation(),
    onSuccess: async () => {
      await invalidateTasksCache()
      await invalidateStatsCache()
    },
  })

  // 添加前置依赖
  const { mutateAsync: addPredecessor, asyncStatus: addPredecessorStatus } = useMutation({
    ...addTaskPredecessorMutation(),
    onSuccess: (_data, vars) => invalidatePredecessorCaches(vars),
  })

  // 删除前置依赖
  const { mutateAsync: removePredecessor, asyncStatus: removePredecessorStatus } = useMutation({
    ...removeTaskPredecessorMutation(),
    onSuccess: (_data, vars) => invalidatePredecessorCaches(vars),
  })

  // 更新前置依赖（依赖类型 / 延迟天数）
  const { mutateAsync: updatePredecessor, asyncStatus: updatePredecessorStatus } = useMutation({
    ...updateTaskPredecessorMutation(),
    onSuccess: (_data, vars) => invalidatePredecessorCaches(vars),
  })

  // 获取可选前置任务（需要传入 taskId）
  const useAvailablePredecessors = (taskId: Ref<number | undefined>) => {
    const enabled = computed(() => taskId.value !== undefined)

    const {
      state: availableState,
      asyncStatus: availableAsyncStatus,
      error: availableError,
      refetch: refetchAvailable,
    } = useQuery(() => {
      const id = taskId.value
      if (id === undefined) {
        return undefined as unknown as ReturnType<typeof getAvailablePredecessorsQuery>
      }
      return {
        ...getAvailablePredecessorsQuery({
          path: { project_id: currentProjectId.value!, id },
        }),
        enabled: enabled.value,
      }
    })

    const availablePredecessors = computed(() => availableState.value?.data ?? [])
    const isLoadingAvailable = computed(() => availableAsyncStatus.value === 'loading')

    return {
      availablePredecessors,
      isLoadingAvailable,
      availableError,
      refetchAvailable,
    }
  }

  const isSubmitting = computed(
    () => createStatus.value === 'loading' || updateStatus.value === 'loading',
  )

  const isDeleting = computed(() => deleteStatus.value === 'loading')

  const isModifyingPredecessor = computed(
    () =>
      addPredecessorStatus.value === 'loading' ||
      removePredecessorStatus.value === 'loading' ||
      updatePredecessorStatus.value === 'loading',
  )

  return {
    // 查询相关
    tasks,
    isLoadingTasks,
    tasksError,
    refreshTasks,

    // 统计信息
    stats,
    isLoadingStats,
    statsError,
    refreshStats,

    // Mutation 相关
    createTask,
    updateTask,
    deleteTask,
    addPredecessor,
    removePredecessor,
    updatePredecessor,

    // Loading 状态
    isSubmitting,
    isDeleting,
    isModifyingPredecessor,

    // 可选前置任务查询（需要传入 taskId）
    useAvailablePredecessors,
  }
}
