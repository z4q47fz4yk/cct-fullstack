import { computed } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import {
  listProjectsQuery,
  listProjectsQueryKey,
  createProjectMutation,
  getProjectQuery,
  getProjectQueryKey,
  updateProjectMutation,
  deleteProjectMutation,
} from '@/client/@pinia/colada.gen'
import type { ProjectCreate, ProjectUpdate } from '@/client/types.gen'

/**
 * 单项目查询（getProject）的缓存新鲜度阈值。
 * 项目元数据很少变化，且 updateProject/deleteProject 会主动 invalidate，
 * 因此可放宽 staleTime 以复用缓存，减少切换页面时的重复请求。
 */
export const PROJECT_QUERY_STALE_MS = 60_000

/**
 * 项目管理 API 封装
 *
 * 提供两类能力：
 * 1. 项目列表 / 创建（首页 `useProjectApi()` 调用）
 * 2. 项目作用域的 单项目查询、更新、删除（`/project/[projectId]/**` 页面调用）
 *
 * 项目作用域的能力在没有当前 projectId 时安全降级（查询 disabled，mutation 抛错）
 */
export function useProjectApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  // ── 列表 + 创建 ─────────────────────────────────────
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listProjectsQuery({
      query: { page: 1, per_page: FETCH_ALL_PAGE_SIZE },
    }),
  )

  const projects = computed(() => state.value?.data?.items ?? [])
  const total = computed(() => state.value?.data?.total ?? 0)
  const isLoading = computed(() => asyncStatus.value === 'loading')

  const { mutateAsync: createProjectRaw, asyncStatus: createStatus } = useMutation({
    ...createProjectMutation(),
    onSuccess: async () => {
      await queryCache.invalidateQueries({ key: listProjectsQueryKey() })
    },
  })

  const isCreating = computed(() => createStatus.value === 'loading')

  async function createNewProject(data: ProjectCreate) {
    return await createProjectRaw({ body: data })
  }

  // ── 单项目（getProject）────────────────────────────────
  const {
    state: projectState,
    asyncStatus: projectStatus,
    error: projectError,
    refresh: refreshProject,
  } = useQuery(() => ({
    ...getProjectQuery({
      path: { id: currentProjectId.value ?? -1 },
    }),
    enabled: currentProjectId.value !== null,
    staleTime: PROJECT_QUERY_STALE_MS,
  }))

  const project = computed(() => projectState.value?.data ?? null)
  const isLoadingProject = computed(
    () => currentProjectId.value !== null && projectStatus.value === 'loading',
  )

  async function invalidateProject() {
    const id = currentProjectId.value
    if (id === null) return
    await queryCache.invalidateQueries({
      key: getProjectQueryKey({ path: { id } }),
    })
  }

  // ── 更新项目 ─────────────────────────────────────────
  const {
    mutateAsync: updateProjectRaw,
    asyncStatus: updateStatus,
    error: updateError,
  } = useMutation({
    ...updateProjectMutation(),
    onSuccess: invalidateProject,
  })

  const isUpdatingProject = computed(() => updateStatus.value === 'loading')

  async function updateProject(body: ProjectUpdate) {
    const id = currentProjectId.value
    if (id === null) throw new Error('当前不在项目上下文中')
    return await updateProjectRaw({ path: { id }, body })
  }

  // ── 删除项目 ─────────────────────────────────────────
  const { mutateAsync: deleteProjectRaw, asyncStatus: deleteStatus } = useMutation({
    ...deleteProjectMutation(),
    onSuccess: async () => {
      await queryCache.invalidateQueries({ key: listProjectsQueryKey() })
      await invalidateProject()
    },
  })

  const isDeletingProject = computed(() => deleteStatus.value === 'loading')

  async function deleteProject() {
    const id = currentProjectId.value
    if (id === null) throw new Error('当前不在项目上下文中')
    return await deleteProjectRaw({ path: { id } })
  }

  return {
    // 列表 + 创建
    projects,
    total,
    isLoading,
    error,
    refresh,
    createProject: createNewProject,
    isCreating,

    // 单项目查询
    project,
    isLoadingProject,
    projectError,
    refreshProject,

    // 更新 / 删除
    updateProject,
    isUpdatingProject,
    updateError,
    deleteProject,
    isDeletingProject,

    // 当前项目上下文（只读）
    currentProjectId,
  }
}
