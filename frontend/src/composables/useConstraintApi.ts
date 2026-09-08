import { computed } from 'vue'
import { useMutation } from '@pinia/colada'
import {
  createResourceConstraintMutation,
  updateResourceConstraintMutation,
  deleteResourceConstraintMutation,
} from '@/client/@pinia/colada.gen'

/**
 * 资源限制 API 封装（仅 mutation）
 *
 * 列表查询已统一到 `useResourceApi`（listResourcesQuery 的 include_constraint 选项）。
 * 资源管理页通过 `useResourceApi({ includeConstraint: true })` 在 list 响应里
 * 直接拿到每条资源附带的 `constraint` 字段，无需自行拼装 Map。
 *
 * 本 composable 仅承担 CRUD 写入；创建/更新/删除成功后由调用方失效资源列表缓存
 * （资源页 saveResource / handleDeleteResource 自行 refresh useResourceApi）。
 */
export function useConstraintApi() {
  // 创建资源限制
  const { mutateAsync: createConstraint, asyncStatus: createStatus } = useMutation({
    ...createResourceConstraintMutation(),
  })

  // 更新资源限制
  const { mutateAsync: updateConstraint, asyncStatus: updateStatus } = useMutation({
    ...updateResourceConstraintMutation(),
  })

  // 删除资源限制
  const { mutateAsync: deleteConstraint, asyncStatus: deleteStatus } = useMutation({
    ...deleteResourceConstraintMutation(),
  })

  const isSubmitting = computed(
    () =>
      createStatus.value === 'loading' ||
      updateStatus.value === 'loading' ||
      deleteStatus.value === 'loading',
  )

  return {
    createConstraint,
    updateConstraint,
    deleteConstraint,
    isSubmitting,
  }
}
