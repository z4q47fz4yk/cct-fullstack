import { computed, readonly } from 'vue'
import { useRoute } from 'vue-router'

/**
 * 提供当前项目上下文，从路由参数 `projectId` 提取。
 * 所有项目范围的 composables 从这里获取 projectId，并通过
 * `path: { project_id: currentProjectId.value! }` 传入 API。
 */
export function useProjectContext() {
  const route = useRoute()
  const projectIdParam = computed(() => (route.params as { projectId?: string }).projectId)

  const currentProjectId = computed(() => {
    const id = projectIdParam.value
    if (!id) return null
    const parsed = Number(id)
    return Number.isNaN(parsed) ? null : parsed
  })

  const isInProject = computed(() => currentProjectId.value !== null)

  return {
    currentProjectId: readonly(currentProjectId),
    isInProject,
  }
}
