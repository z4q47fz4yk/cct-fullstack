import { computed } from 'vue'
import type { Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type { TagCreate, TagResp, TagUpdate } from '@/client/types.gen'
import {
  createTagMutation,
  updateTagMutation,
  deleteTagMutation,
  getTagResourcesQuery,
  listTagGroupsQuery,
  listTagGroupsQueryKey,
  listTagsQuery,
  listTagsQueryKey,
} from '@/client/@pinia/colada.gen'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'

/**
 * 扁平标签 API 封装（group 为纯展示分组）
 *
 * - `tags`：项目内全部标签（一次拉全量，量级很小），按 (group, name) 排序
 * - CRUD：创建携带 group（空=未分组）；删除/改名后端即时生效
 */
export function useTagApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const invalidateTags = async () => {
    await queryCache.invalidateQueries({
      key: listTagsQueryKey({ path: { project_id: currentProjectId.value! } }),
    })
    await queryCache.invalidateQueries({
      key: listTagGroupsQueryKey({ path: { project_id: currentProjectId.value! } }),
    })
  }

  // 项目内全部标签（分页一次取满）
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listTagsQuery({
      path: { project_id: currentProjectId.value! },
      query: { per_page: FETCH_ALL_PAGE_SIZE },
    }),
  )

  const tags = computed<TagResp[]>(() => state.value?.data?.items ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')

  const { mutateAsync: createTag, asyncStatus: createStatus } = useMutation({
    ...createTagMutation(),
    onSuccess: invalidateTags,
  })

  const { mutateAsync: updateTag, asyncStatus: updateStatus } = useMutation({
    ...updateTagMutation(),
    onSuccess: invalidateTags,
  })

  const { mutateAsync: deleteTag, asyncStatus: deleteStatus } = useMutation({
    ...deleteTagMutation(),
    onSuccess: invalidateTags,
  })

  const isSubmitting = computed(
    () =>
      createStatus.value === 'loading' ||
      updateStatus.value === 'loading' ||
      deleteStatus.value === 'loading',
  )

  return {
    tags,
    isLoading,
    error,
    refresh,
    createTag,
    updateTag,
    deleteTag,
    isSubmitting,
  }
}

/**
 * 按分组加载标签（分页），供管理页左侧分组 + 右侧标签列表。
 */
export function useTagsByGroup(group: Ref<string>) {
  const { currentProjectId } = useProjectContext()
  const { state, asyncStatus, error, refresh } = useQuery(() => ({
    ...listTagsQuery({
      path: { project_id: currentProjectId.value! },
      query: { group: group.value || undefined, per_page: FETCH_ALL_PAGE_SIZE },
    }),
    enabled: !!currentProjectId.value,
  }))

  const tags = computed(() => state.value?.data?.items ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')
  return { tags, isLoading, error, refresh }
}

/**
 * 标签分组统计（管理页左侧分组列表）。
 */
export function useTagGroups() {
  const { currentProjectId } = useProjectContext()
  const { state, asyncStatus, error, refresh } = useQuery(() => ({
    ...listTagGroupsQuery({ path: { project_id: currentProjectId.value! } }),
    enabled: !!currentProjectId.value,
  }))

  const groups = computed(() => state.value?.data ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')
  return { groups, isLoading, error, refresh }
}

/**
 * 查询标签直接关联的资源（分页）。
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

export type { TagCreate, TagUpdate }
