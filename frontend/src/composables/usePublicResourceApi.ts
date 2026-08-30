import { computed } from 'vue'
import type { Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type {
  ResourcePublicResp,
  ResourcePublicCopyReq,
  ResourcePublicCopyResp,
  ResourceCategory,
} from '@/client/types.gen'
import {
  listPublicResourcesQuery,
  copyPublicResourcesMutation,
  listResourcesQueryKey,
} from '@/client/@pinia/colada.gen'

export interface UsePublicResourcesOptions {
  category: Ref<ResourceCategory>
  searchQuery: Ref<string>
  page: Ref<number>
  pageSize: Ref<number>
}

/**
 * 公共资源（只读字典）查询封装
 *
 * GET /public-resource — 分页、按名称/分类筛选
 *
 * 注意：公共资源列表不依赖 project_id，所以不需要 useProjectContext
 */
export function usePublicResources(options: UsePublicResourcesOptions) {
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listPublicResourcesQuery({
      query: {
        category: options.category.value,
        name: options.searchQuery.value?.trim() || null,
        page: options.page.value,
        per_page: options.pageSize.value,
      },
    }),
  )

  const publicResources = computed<ResourcePublicResp[]>(() => state.value?.data?.items ?? [])
  const totalCount = computed(() => state.value?.data?.total ?? 0)
  const isLoading = computed(() => asyncStatus.value === 'loading')

  return { publicResources, totalCount, isLoading, error, refresh }
}

/**
 * 公共资源批量拷贝到当前项目的 mutation
 *
 * POST /projects/{project_id}/public-resource/batch-copy
 *
 * body 为 ResourcePublicCopyReq，{ ids } 与 { category } 严格互斥。
 * 成功拷贝后刷新项目资源列表缓存。
 */
export function useCopyPublicResources() {
  const { currentProjectId } = useProjectContext()
  const queryCache = useQueryCache()

  const invalidateProjectResources = async () => {
    if (currentProjectId.value == null) return
    await queryCache.invalidateQueries({
      key: listResourcesQueryKey({ path: { project_id: currentProjectId.value } }),
    })
  }

  const { mutateAsync, asyncStatus } = useMutation({
    ...copyPublicResourcesMutation(),
    onSuccess: invalidateProjectResources,
  })

  const copyPublicResources = (body: ResourcePublicCopyReq): Promise<ResourcePublicCopyResp> =>
    mutateAsync({ path: { project_id: currentProjectId.value! }, body })

  const isCopying = computed(() => asyncStatus.value === 'loading')

  return { copyPublicResources, isCopying }
}
