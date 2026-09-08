import { computed } from 'vue'
import { useMutation } from '@pinia/colada'
import {
  createReuseConfigMutation,
  updateReuseConfigMutation,
  deleteReuseConfigMutation,
} from '@/client/@pinia/colada.gen'

/**
 * 可周转材料复用配置 API 封装（仅 mutation）
 *
 * 列表查询已统一到 `useResourceApi`（listResourcesQuery 的 include_reuse_config 选项）。
 * 资源管理页通过 `useResourceApi({ includeReuseConfig: true })` 在 list 响应里
 * 直接拿到每条资源附带的 `reuse_config` 字段，无需自行拼装 Map。
 *
 * 本 composable 仅承担 CRUD 写入；创建/更新/删除成功后由调用方失效资源列表缓存。
 */
export function useReuseConfigApi() {
  // 创建复用配置
  const { mutateAsync: createConfig, asyncStatus: createStatus } = useMutation({
    ...createReuseConfigMutation(),
  })

  // 更新复用配置
  const { mutateAsync: updateConfig, asyncStatus: updateStatus } = useMutation({
    ...updateReuseConfigMutation(),
  })

  // 删除复用配置
  const { mutateAsync: deleteConfig, asyncStatus: deleteStatus } = useMutation({
    ...deleteReuseConfigMutation(),
  })

  const isSubmitting = computed(
    () =>
      createStatus.value === 'loading' ||
      updateStatus.value === 'loading' ||
      deleteStatus.value === 'loading',
  )

  return {
    createConfig,
    updateConfig,
    deleteConfig,
    isSubmitting,
  }
}
