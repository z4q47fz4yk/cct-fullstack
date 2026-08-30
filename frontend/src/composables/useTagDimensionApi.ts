import { computed } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type { TagDimensionCreate, TagDimensionUpdate } from '@/client/types.gen'
import {
  listTagDimensionsQuery,
  listTagDimensionsQueryKey,
  createTagDimensionMutation,
  updateTagDimensionMutation,
  deleteTagDimensionMutation,
} from '@/client/@pinia/colada.gen'

/**
 * 标签维度 API 封装
 * 维度 CRUD；删除含标签的维度时后端返回 409（由全局错误拦截 toast 展示）
 */
export function useTagDimensionApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const invalidateDimensions = async () => {
    await queryCache.invalidateQueries({
      key: listTagDimensionsQueryKey({ path: { project_id: currentProjectId.value! } }),
    })
  }

  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listTagDimensionsQuery({ path: { project_id: currentProjectId.value! } }),
  )

  const dimensions = computed(() => state.value?.data?.items ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')

  const { mutateAsync: createDimension, asyncStatus: createStatus } = useMutation({
    ...createTagDimensionMutation(),
    onSuccess: invalidateDimensions,
  })

  const { mutateAsync: updateDimension, asyncStatus: updateStatus } = useMutation({
    ...updateTagDimensionMutation(),
    onSuccess: invalidateDimensions,
  })

  const { mutateAsync: deleteDimension, asyncStatus: deleteStatus } = useMutation({
    ...deleteTagDimensionMutation(),
    onSuccess: invalidateDimensions,
  })

  const isSubmitting = computed(
    () =>
      createStatus.value === 'loading' ||
      updateStatus.value === 'loading' ||
      deleteStatus.value === 'loading',
  )

  return {
    dimensions,
    isLoading,
    error,
    refresh,
    createDimension,
    updateDimension,
    deleteDimension,
    isSubmitting,
  }
}

export type { TagDimensionCreate, TagDimensionUpdate }
