/**
 * 天气月度记录 API 封装
 *
 * month 必须为每月 1 日；同月唯一（重复创建 409）；PUT 不可改 month。
 */
import { computed, type Ref } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import type { WeatherCreate, WeatherUpdate } from '@/client/types.gen'
import {
  listWeatherQuery,
  listWeatherQueryKey,
  createWeatherMutation,
  updateWeatherMutation,
  deleteWeatherMutation,
} from '@/client/@pinia/colada.gen'

export interface WeatherRange {
  startMonth?: string | null
  endMonth?: string | null
}

export function useWeatherApi(range: Ref<WeatherRange> = computed(() => ({}))) {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  const listQuery = useQuery(() => ({
    ...listWeatherQuery({
      path: { project_id: currentProjectId.value! },
      query: {
        startMonth: range.value.startMonth || null,
        endMonth: range.value.endMonth || null,
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

  return {
    weather,
    isLoading,
    createRecord,
    updateRecord,
    deleteRecord,
    isSubmitting:
      createMutation.isLoading.value ||
      updateMutation.isLoading.value ||
      deleteMutation.isLoading.value,
    refresh: listQuery.refresh,
  }
}

export type { WeatherCreate, WeatherUpdate }
