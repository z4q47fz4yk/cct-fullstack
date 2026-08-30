import { computed } from 'vue'
import { useStorage } from '@vueuse/core'
import { useProjectContext } from '@/composables/useProjectContext'

/**
 * 创建项目范围的 localStorage 存储
 * 自动用 projectId 前缀 key，实现不同项目的数据隔离
 *
 * 当 projectId 为 null 时（如项目列表页），回退到原始 key（向后兼容）
 */
export function useProjectStorage<T>(baseKey: string, defaultValue: T) {
  const { currentProjectId } = useProjectContext()

  const storageKey = computed(() =>
    currentProjectId.value !== null ? `${baseKey}:${currentProjectId.value}` : baseKey,
  )

  return useStorage<T>(storageKey, defaultValue)
}
