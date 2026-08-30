import { computed } from 'vue'
import type { Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import {
  getResourceTagsQuery,
  getResourceTagsQueryKey,
  setResourceTagsMutation,
  listResourcesQueryKey,
} from '@/client/@pinia/colada.gen'

/**
 * 资源打标 API 封装
 * 获取/替换式设置资源的标签；互斥校验冲突（409）会向上抛出 ApiError，供界面内联展示
 */
export function useResourceTagApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const invalidateResourceTags = async (resourceId: number) => {
    await queryCache.invalidateQueries({
      key: getResourceTagsQueryKey({
        path: { project_id: currentProjectId.value!, resource_id: resourceId },
      }),
    })
    // 资源列表（include_tags）也携带标签，需一并刷新
    await queryCache.invalidateQueries({
      key: listResourcesQueryKey({ path: { project_id: currentProjectId.value! } }),
    })
  }

  // 替换式设置资源标签（409 互斥冲突时 reject ApiError）
  const { mutateAsync: setResourceTags, asyncStatus: setStatus } = useMutation({
    ...setResourceTagsMutation(),
    onSuccess: (_data, vars) => invalidateResourceTags(vars.path.resource_id),
  })

  const isSetting = computed(() => setStatus.value === 'loading')

  return { setResourceTags, isSetting }
}

/**
 * 查询资源当前挂载的标签。
 * resourceId 为 null 时查询挂起。
 */
export function useResourceTags(resourceId: Ref<number | null>) {
  const { currentProjectId } = useProjectContext()
  const { state, asyncStatus, error, refresh } = useQuery(() => ({
    ...getResourceTagsQuery({
      path: { project_id: currentProjectId.value!, resource_id: resourceId.value! },
    }),
    enabled: resourceId.value !== null,
  }))

  const tags = computed(() => state.value?.data ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')

  return { tags, isLoading, error, refresh }
}
