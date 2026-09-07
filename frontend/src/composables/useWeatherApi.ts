/**
 * 天气日记录 API 封装
 *
 * 日粒度：date 为任意自然日；同天唯一（重复创建 409）；PUT 不可改 date。
 * 数据可来自手工录入或 Open-Meteo 同步（isSynced 标记）。
 */
import { computed, type Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import type {
  WeatherCreate,
  WeatherSyncRequest,
  WeatherSyncResp,
  WeatherUpdate,
} from '@/client/types.gen'
import {
  listWeatherQuery,
  listWeatherQueryKey,
  createWeatherMutation,
  updateWeatherMutation,
  deleteWeatherMutation,
  syncWeatherMutation,
} from '@/client/@pinia/colada.gen'

export interface WeatherRange {
  startDate?: string | null
  endDate?: string | null
}

export function useWeatherApi(range: Ref<WeatherRange> = computed(() => ({}))) {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const listQuery = useQuery(() => ({
    ...listWeatherQuery({
      path: { project_id: currentProjectId.value! },
      query: {
        startDate: range.value.startDate || null,
        endDate: range.value.endDate || null,
        per_page: FETCH_ALL_PAGE_SIZE,
      },
    }),
    enabled: !!currentProjectId.value,
  }))

  const weather = computed(() => listQuery.state.value?.data?.items ?? [])
  const isLoading = computed(() => listQuery.asyncStatus.value === 'loading')

  async function invalidate() {
    await queryCache.invalidateQueries({
      key: listWeatherQueryKey({ path: { project_id: currentProjectId.value! } }),
    })
  }

  const createMutation = useMutation({
    ...createWeatherMutation(),
    onSuccess: invalidate,
  })
  const updateMutation = useMutation({
    ...updateWeatherMutation(),
    onSuccess: invalidate,
  })
  const deleteMutation = useMutation({
    ...deleteWeatherMutation(),
    onSuccess: invalidate,
  })
  const syncMutation = useMutation({
    ...syncWeatherMutation(),
    onSuccess: invalidate,
  })

  async function createRecord(body: WeatherCreate) {
    return createMutation.mutateAsync({
      path: { project_id: currentProjectId.value! },
      body,
    })
  }

  async function updateRecord(id: number, body: WeatherUpdate) {
    return updateMutation.mutateAsync({
      path: { project_id: currentProjectId.value!, id },
      body,
    })
  }

  async function deleteRecord(id: number) {
    return deleteMutation.mutateAsync({
      path: { project_id: currentProjectId.value!, id },
    })
  }

  /** 触发 Open-Meteo 历史天气同步；返回响应（含 synced/skipped/message）。 */
  async function syncWeather(body: WeatherSyncRequest): Promise<WeatherSyncResp> {
    return syncMutation.mutateAsync({
      path: { project_id: currentProjectId.value! },
      body,
    })
  }

  return {
    weather,
    isLoading,
    createRecord,
    updateRecord,
    deleteRecord,
    syncWeather,
    isSyncing: syncMutation.isLoading.value,
    isSubmitting:
      createMutation.isLoading.value ||
      updateMutation.isLoading.value ||
      deleteMutation.isLoading.value ||
      syncMutation.isLoading.value,
    refresh: listQuery.refresh,
  }
}

export type { WeatherCreate, WeatherUpdate, WeatherSyncRequest, WeatherSyncResp }
