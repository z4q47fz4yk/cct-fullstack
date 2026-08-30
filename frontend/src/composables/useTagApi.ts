import { computed } from 'vue'
import type { Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type { TagCreate, TagUpdate } from '@/client/types.gen'
import {
  getTagTreeQuery,
  getTagTreeQueryKey,
  createTagMutation,
  updateTagMutation,
  deleteTagMutation,
  getTagResourcesQuery,
} from '@/client/@pinia/colada.gen'

/**
 * 碳排放标签 API 封装
 *
 * - `tagTree`：全维度标签树（多棵根树，供图表/打标选择器按维度分组展示）
 * - CRUD：创建必须携带 dimensionId；删除含子标签时后端拒绝
 */
export function useTagApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const invalidateTree = async () => {
    await queryCache.invalidateQueries({
      key: getTagTreeQueryKey({ path: { project_id: currentProjectId.value! } }),
    })
  }

  // 全维度标签树
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    getTagTreeQuery({ path: { project_id: currentProjectId.value! } }),
  )

  const tagTree = computed(() => state.value?.data ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')

  // 创建标签
  const { mutateAsync: createTag, asyncStatus: createStatus } = useMutation({
    ...createTagMutation(),
    onSuccess: invalidateTree,
  })

  // 更新标签（parentId 省略=保持当前父级，显式 null=移到顶级）
  const { mutateAsync: updateTag, asyncStatus: updateStatus } = useMutation({
    ...updateTagMutation(),
    onSuccess: invalidateTree,
  })

  // 删除标签
  const { mutateAsync: deleteTag, asyncStatus: deleteStatus } = useMutation({
    ...deleteTagMutation(),
    onSuccess: invalidateTree,
  })

  const isSubmitting = computed(
    () =>
      createStatus.value === 'loading' ||
      updateStatus.value === 'loading' ||
      deleteStatus.value === 'loading',
  )

  return {
    tagTree,
    isLoading,
    error,
    refresh,
    createTag,
    updateTag,
    deleteTag,
    isSubmitting,
  }
}

export type { TagCreate, TagUpdate }

/**
 * 按维度查询标签树（标签管理页：左侧维度 → 右侧该维度树）。
 * dimensionId 为 null 时查询挂起。
 */
export function useTagTreeByDimension(dimensionId: Ref<number | null>) {
  const { currentProjectId } = useProjectContext()
  const { state, asyncStatus, error, refresh } = useQuery(() => ({
    ...getTagTreeQuery({
      path: { project_id: currentProjectId.value! },
      query: { dimensionId: dimensionId.value ?? undefined },
    }),
    enabled: dimensionId.value !== null,
  }))

  const tagTree = computed(() => state.value?.data ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')

  return { tagTree, isLoading, error, refresh }
}

/**
 * 查询标签直接关联的资源（分页，不含子标签）。
 * 供标签详情页使用，跟随 selectedTagId 自动切换。
 */
export function useTagResources(
  tagId: Ref<number | null>,
  page: Ref<number>,
  pageSize: Ref<number>,
) {
  const { currentProjectId } = useProjectContext()
  const { state, asyncStatus, error, refresh } = useQuery(() => ({
    ...getTagResourcesQuery({
      path: { project_id: currentProjectId.value!, id: tagId.value! },
      query: { page: page.value, per_page: pageSize.value },
    }),
    enabled: tagId.value !== null,
  }))

  const resources = computed(() => state.value?.data?.items ?? [])
  const totalCount = computed(() => state.value?.data?.total ?? 0)
  const isLoading = computed(() => asyncStatus.value === 'loading')

  return { resources, totalCount, isLoading, error, refresh }
}
