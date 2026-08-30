import { computed } from 'vue'
import type { Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import type { ChartCreate, ChartUpdate } from '@/client/types.gen'
import {
  listChartsQuery,
  listChartsQueryKey,
  createChartMutation,
  updateChartMutation,
  deleteChartMutation,
  setChartTagsMutation,
  getChartPieDataQuery,
} from '@/client/@pinia/colada.gen'

/**
 * 碳排放图表定义 API 封装
 * 提供图表列表、CRUD、切片绑定与饼图数据查询
 */
export function useChartApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const invalidateCharts = async () => {
    await queryCache.invalidateQueries({
      key: listChartsQueryKey({ path: { project_id: currentProjectId.value! } }),
    })
    // 图表定义变化会改变所有饼图数据
    await queryCache.invalidateQueries({ key: ['getChartPieData'] })
  }

  // 图表列表（一次拉全量，图表数量级很小）
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listChartsQuery({
      path: { project_id: currentProjectId.value! },
      query: { per_page: FETCH_ALL_PAGE_SIZE },
    }),
  )

  const charts = computed(() => state.value?.data?.items ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')

  // 创建图表
  const { mutateAsync: createChart, asyncStatus: createStatus } = useMutation({
    ...createChartMutation(),
    onSuccess: invalidateCharts,
  })

  // 更新图表
  const { mutateAsync: updateChart, asyncStatus: updateStatus } = useMutation({
    ...updateChartMutation(),
    onSuccess: invalidateCharts,
  })

  // 替换式设置图表绑定的标签（顺序即 sortOrder）
  const { mutateAsync: setChartTags, asyncStatus: tagsStatus } = useMutation({
    ...setChartTagsMutation(),
    onSuccess: invalidateCharts,
  })

  // 删除图表
  const { mutateAsync: deleteChart, asyncStatus: deleteStatus } = useMutation({
    ...deleteChartMutation(),
    onSuccess: invalidateCharts,
  })

  const isSubmitting = computed(
    () =>
      createStatus.value === 'loading' ||
      updateStatus.value === 'loading' ||
      tagsStatus.value === 'loading' ||
      deleteStatus.value === 'loading',
  )

  return {
    charts,
    isLoading,
    error,
    refresh,
    createChart,
    updateChart,
    setChartTags,
    deleteChart,
    isSubmitting,
  }
}

export type { ChartCreate, ChartUpdate }

/**
 * 查询单个图表的饼图数据（按 sortOrder 升序返回）。
 * chartId 为 null 时查询挂起（enabled=false）。
 */
export type ChartPieMetric = 'emission' | 'cost'

export function useChartPieData(
  chartId: Ref<number | null>,
  metric: Ref<ChartPieMetric> = computed(() => 'emission'),
) {
  const { currentProjectId } = useProjectContext()
  const { state, asyncStatus, error, refresh } = useQuery(() => ({
    ...getChartPieDataQuery({
      path: { project_id: currentProjectId.value!, id: chartId.value! },
      // 后端默认 ACTUAL（实际用量口径），显式传参避免歧义
      query: { metric: metric.value, usageType: 'ACTUAL' },
    }),
    enabled: chartId.value !== null,
  }))

  const slices = computed(() => state.value?.data ?? [])
  const isLoading = computed(() => asyncStatus.value === 'loading')
  const totalEmission = computed(() => slices.value.reduce((sum, s) => sum + (s.value ?? 0), 0))

  return { slices, totalEmission, isLoading, error, refresh }
}
