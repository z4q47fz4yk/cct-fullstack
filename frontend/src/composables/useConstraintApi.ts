import { computed } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type { ResourceConstraintResp } from '@/types/constraint'
import {
  listResourceConstraintsQuery,
  listResourceConstraintsQueryKey,
  createResourceConstraintMutation,
  updateResourceConstraintMutation,
  deleteResourceConstraintMutation,
} from '@/client/@pinia/colada.gen'

/**
 * 资源限制 API 封装
 * 提供资源限制的 CRUD 操作和缓存管理
 */
export function useConstraintApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  /**
   * 缓存失效函数
   * 用于在创建、更新、删除操作后刷新列表缓存
   */
  const invalidateConstraintsCache = async () => {
    await queryCache.invalidateQueries({
      key: listResourceConstraintsQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  }

  // 查询资源限制列表
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listResourceConstraintsQuery({
      path: { project_id: currentProjectId.value! },
    }),
  )

  const constraints = computed<ResourceConstraintResp[]>(() => state.value?.data?.items ?? [])
  const totalConstraints = computed(() => state.value?.data?.total ?? 0)
  const isLoading = computed(() => asyncStatus.value === 'loading')

  // 创建资源限制
  const { mutateAsync: createConstraint, asyncStatus: createStatus } = useMutation({
    ...createResourceConstraintMutation(),
    onSuccess: invalidateConstraintsCache,
  })

  // 更新资源限制
  const { mutateAsync: updateConstraint, asyncStatus: updateStatus } = useMutation({
    ...updateResourceConstraintMutation(),
    onSuccess: invalidateConstraintsCache,
  })

  // 删除资源限制
  const { mutateAsync: deleteConstraint, asyncStatus: deleteStatus } = useMutation({
    ...deleteResourceConstraintMutation(),
    onSuccess: invalidateConstraintsCache,
  })

  const isSubmitting = computed(
    () =>
      createStatus.value === 'loading' ||
      updateStatus.value === 'loading' ||
      deleteStatus.value === 'loading',
  )

  return {
    // 查询相关
    constraints,
    totalConstraints,
    isLoading,
    error,
    refresh,
    // Mutation 相关
    createConstraint,
    updateConstraint,
    deleteConstraint,
    isSubmitting,
    // 缓存管理
    invalidateConstraintsCache,
  }
}

// 导出查询 Key 函数，供外部使用
export { listResourceConstraintsQueryKey }
