import { useQuery } from '@pinia/colada'
import { aiUsageQuery } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'

/**
 * 项目 AI 对话成本审计查询。
 * 展示项目累计 AI 成本 + 最近记录。
 */
export function useAiUsage() {
  const { currentProjectId } = useProjectContext()

  const { data, asyncStatus, isLoading, refresh } = useQuery(() => ({
    ...aiUsageQuery({
      path: { project_id: currentProjectId.value! },
    }),
    enabled: currentProjectId.value !== null,
    staleTime: 30_000,
  }))

  return { data, asyncStatus, isLoading, refresh }
}
