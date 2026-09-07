import { computed } from 'vue'
import type { Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import {
  getResourceTagsQuery,
  getResourceTagsQueryKey,
  setResourceTagsMutation,
  addResourceTagMutation,
  removeResourceTagMutation,
  getTaskTagsQuery,
  getTaskTagsQueryKey,
  setTaskTagsMutation,
  addTaskTagMutation,
  removeTaskTagMutation,
  getUsageTagsQuery,
  getUsageTagsQueryKey,
  setUsageTagsMutation,
  addUsageTagMutation,
  removeUsageTagMutation,
  listResourcesQueryKey,
  listTasksQueryKey,
  listResourceUsagesQueryKey,
} from '@/client/@pinia/colada.gen'

/** 可打标实体类型 */
export type TagEntityType = 'resource' | 'task' | 'usage'

export interface TagEntityRef {
  type: TagEntityType
  id: number
}

/** 按实体类型取当前标签列表查询（entity 为 null 时挂起） */
export function useEntityTags(entity: Ref<TagEntityRef | null>) {
  const { currentProjectId } = useProjectContext()
  const { state, asyncStatus, error, refresh } = useQuery(() => {
    const e = entity.value
    if (!e || !currentProjectId.value) {
      // 挂起态：复用资源查询骨架，enabled=false
      return {
        ...getResourceTagsQuery({ path: { project_id: 0, resource_id: 0 } }),
        enabled: false,
      }
    }
    const base = { path: { project_id: currentProjectId.value } }
    switch (e.type) {
      case 'resource':
        return {
          ...getResourceTagsQuery({ ...base, path: { ...base.path, resource_id: e.id } }),
          enabled: true,
        }
      case 'task':
        return {
          ...getTaskTagsQuery({ ...base, path: { ...base.path, task_id: e.id } }),
          enabled: true,
        }
      case 'usage':
        return {
          ...getUsageTagsQuery({ ...base, path: { ...base.path, usage_id: e.id } }),
          enabled: true,
        }
    }
  })

  const tags = computed(() => state.value?.data ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')

  return { tags, isLoading, error, refresh }
}

/**
 * 实体打标 API（资源/任务/用量统一）
 * 支持三种写语义：
 * - setTags：整组替换（PUT，默认分类标签被后端静默忽略）
 * - addTag：单点新增（POST /tags/{tag_id}，幂等；默认分类标签 no-op）
 * - removeTag：单点删除（DELETE /tags/{tag_id}，幂等；tag 不存在由后端 404）
 * 错误（422/404）向上抛出 ApiError（detail 含原因），供界面内联展示。
 * 不做图表切片互斥校验（冲突检查在数据体检）。
 */
export function useEntityTagApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const invalidateEntityTags = async (entity: TagEntityRef) => {
    const projectId = currentProjectId.value!
    const key:
      | ReturnType<typeof getResourceTagsQueryKey>
      | ReturnType<typeof getTaskTagsQueryKey>
      | ReturnType<typeof getUsageTagsQueryKey> =
      entity.type === 'resource'
        ? getResourceTagsQueryKey({ path: { project_id: projectId, resource_id: entity.id } })
        : entity.type === 'task'
          ? getTaskTagsQueryKey({ path: { project_id: projectId, task_id: entity.id } })
          : getUsageTagsQueryKey({ path: { project_id: projectId, usage_id: entity.id } })
    await queryCache.invalidateQueries({ key })
    // 列表（include_tags）携带标签，需一并刷新
    if (entity.type === 'resource') {
      await queryCache.invalidateQueries({
        key: listResourcesQueryKey({ path: { project_id: projectId } }),
      })
    } else if (entity.type === 'task') {
      await queryCache.invalidateQueries({
        key: listTasksQueryKey({ path: { project_id: projectId } }),
      })
    } else {
      await queryCache.invalidateQueries({
        key: listResourceUsagesQueryKey({ path: { project_id: projectId } }),
      })
    }
  }

  const { mutateAsync: setResourceTags, asyncStatus: resourceStatus } = useMutation({
    ...setResourceTagsMutation(),
    onSuccess: (_data, vars) =>
      invalidateEntityTags({ type: 'resource', id: vars.path.resource_id }),
  })
  const { mutateAsync: addResourceTag } = useMutation({
    ...addResourceTagMutation(),
    onSuccess: (_data, vars) =>
      invalidateEntityTags({ type: 'resource', id: vars.path.resource_id }),
  })
  const { mutateAsync: removeResourceTag } = useMutation({
    ...removeResourceTagMutation(),
    onSuccess: (_data, vars) =>
      invalidateEntityTags({ type: 'resource', id: vars.path.resource_id }),
  })

  const { mutateAsync: setTaskTags, asyncStatus: taskStatus } = useMutation({
    ...setTaskTagsMutation(),
    onSuccess: (_data, vars) => invalidateEntityTags({ type: 'task', id: vars.path.task_id }),
  })
  const { mutateAsync: addTaskTag } = useMutation({
    ...addTaskTagMutation(),
    onSuccess: (_data, vars) => invalidateEntityTags({ type: 'task', id: vars.path.task_id }),
  })
  const { mutateAsync: removeTaskTag } = useMutation({
    ...removeTaskTagMutation(),
    onSuccess: (_data, vars) => invalidateEntityTags({ type: 'task', id: vars.path.task_id }),
  })

  const { mutateAsync: setUsageTags, asyncStatus: usageStatus } = useMutation({
    ...setUsageTagsMutation(),
    onSuccess: (_data, vars) => invalidateEntityTags({ type: 'usage', id: vars.path.usage_id }),
  })
  const { mutateAsync: addUsageTag } = useMutation({
    ...addUsageTagMutation(),
    onSuccess: (_data, vars) => invalidateEntityTags({ type: 'usage', id: vars.path.usage_id }),
  })
  const { mutateAsync: removeUsageTag } = useMutation({
    ...removeUsageTagMutation(),
    onSuccess: (_data, vars) => invalidateEntityTags({ type: 'usage', id: vars.path.usage_id }),
  })

  const isSetting = computed(
    () =>
      resourceStatus.value === 'loading' ||
      taskStatus.value === 'loading' ||
      usageStatus.value === 'loading',
  )

  async function setTags(entity: TagEntityRef, tagIds: number[], silent = true) {
    const projectId = currentProjectId.value!
    if (entity.type === 'resource') {
      await setResourceTags({
        path: { project_id: projectId, resource_id: entity.id },
        body: { tagIds },
        silent,
      })
    } else if (entity.type === 'task') {
      await setTaskTags({
        path: { project_id: projectId, task_id: entity.id },
        body: { tagIds },
        silent,
      })
    } else {
      await setUsageTags({
        path: { project_id: projectId, usage_id: entity.id },
        body: { tagIds },
        silent,
      })
    }
  }

  async function addTag(entity: TagEntityRef, tagId: number, silent = true) {
    const projectId = currentProjectId.value!
    if (entity.type === 'resource') {
      await addResourceTag({
        path: { project_id: projectId, resource_id: entity.id, tag_id: tagId },
        silent,
      })
    } else if (entity.type === 'task') {
      await addTaskTag({
        path: { project_id: projectId, task_id: entity.id, tag_id: tagId },
        silent,
      })
    } else {
      await addUsageTag({
        path: { project_id: projectId, usage_id: entity.id, tag_id: tagId },
        silent,
      })
    }
  }

  async function removeTag(entity: TagEntityRef, tagId: number, silent = true) {
    const projectId = currentProjectId.value!
    if (entity.type === 'resource') {
      await removeResourceTag({
        path: { project_id: projectId, resource_id: entity.id, tag_id: tagId },
        silent,
      })
    } else if (entity.type === 'task') {
      await removeTaskTag({
        path: { project_id: projectId, task_id: entity.id, tag_id: tagId },
        silent,
      })
    } else {
      await removeUsageTag({
        path: { project_id: projectId, usage_id: entity.id, tag_id: tagId },
        silent,
      })
    }
  }

  return { setTags, addTag, removeTag, isSetting }
}
