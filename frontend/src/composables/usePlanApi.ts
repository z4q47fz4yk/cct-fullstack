/**
 * 施工计划基线 + 低碳措施 API 封装
 *
 * - plans：估算（不落库）/ 保存基线 / 保存草稿 / 读取（404 = 尚无计划）
 * - measures：ADD（负因子资源）/ REPLACE（计划资源→实际资源）CRUD，
 *   estimatedSaving 随 kind/resourceIds 重算，actualSaving 从 usage 实时聚合
 */
import { computed } from 'vue'
import { useQuery, useMutation, useQueryCache } from '@pinia/colada'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import type {
  MeasureCreate,
  MeasureUpdate,
  PlanEstimateRequest,
  PlanResp,
} from '@/client/types.gen'
import {
  getPlanQuery,
  getPlanQueryKey,
  estimatePlanMutation,
  savePlanMutation,
  savePlanDraftMutation,
  listMeasuresQuery,
  listMeasuresQueryKey,
  createMeasureMutation,
  updateMeasureMutation,
  deleteMeasureMutation,
} from '@/client/@pinia/colada.gen'
import { notifyError } from '@/composables/useToast'

export function usePlanApi() {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  // ──── 计划基线读取（404 = 尚未保存任何计划） ─────────────
  // silent: 404「尚未创建施工计划基线」是正常的空态信号（页面正文已展示引导），
  // 不应走全局错误拦截器弹「资源不存在」误导 toast
  const planQuery = useQuery(() => ({
    ...getPlanQuery({ path: { project_id: currentProjectId.value! }, silent: true }),
    enabled: !!currentProjectId.value,
  }))

  const plan = computed<PlanResp | null>(() => planQuery.state.value?.data ?? null)
  const isLoadingPlan = computed(() => planQuery.asyncStatus.value === 'loading')
  /** 404 = 从未保存计划 */
  const isPlanMissing = computed(() => {
    const e = planQuery.error.value as { status?: number } | null
    return e?.status === 404
  })

  async function invalidatePlan() {
    await queryCache.invalidateQueries({
      key: getPlanQueryKey({ path: { project_id: currentProjectId.value! } }),
    })
  }

  // ──── 计划估算（不落库） ─────────────────────────────────
  const estimateMutation = useMutation(estimatePlanMutation())

  async function estimatePlan(body: PlanEstimateRequest) {
    try {
      const resp = await estimateMutation.mutateAsync({
        path: { project_id: currentProjectId.value! },
        body,
      })
      return resp
    } catch (e) {
      console.error('Estimate plan failed:', e)
      throw e
    }
  }

  // ──── 保存基线 / 草稿 ────────────────────────────────────
  const saveMutation = useMutation(savePlanMutation())
  const saveDraftMutation = useMutation(savePlanDraftMutation())

  async function savePlan(body: PlanEstimateRequest) {
    try {
      const resp = await saveMutation.mutateAsync({
        path: { project_id: currentProjectId.value! },
        body,
      })
      await invalidatePlan()
      return resp
    } catch (e) {
      console.error('Save plan failed:', e)
      throw e
    }
  }

  async function savePlanDraft(body: PlanEstimateRequest) {
    try {
      const resp = await saveDraftMutation.mutateAsync({
        path: { project_id: currentProjectId.value! },
        body,
      })
      await invalidatePlan()
      return resp
    } catch (e) {
      console.error('Save plan draft failed:', e)
      throw e
    }
  }

  // ──── 低碳措施 CRUD ──────────────────────────────────────
  const measuresQuery = useQuery(() => ({
    ...listMeasuresQuery({
      path: { project_id: currentProjectId.value! },
      query: { page: 1, per_page: FETCH_ALL_PAGE_SIZE },
    }),
    enabled: !!currentProjectId.value,
  }))

  const measures = computed(() => measuresQuery.state.value?.data?.items ?? [])
  const isLoadingMeasures = computed(() => measuresQuery.asyncStatus.value === 'loading')

  async function invalidateMeasures() {
    await queryCache.invalidateQueries({
      key: listMeasuresQueryKey({ path: { project_id: currentProjectId.value! } }),
    })
  }

  const createMeasure = useMutation({
    ...createMeasureMutation(),
    onSuccess: invalidateMeasures,
    onError: (e) => {
      console.error('Create measure failed:', e)
      notifyError({ title: '创建措施失败' })
    },
  })

  const updateMeasure = useMutation({
    ...updateMeasureMutation(),
    onSuccess: invalidateMeasures,
    onError: (e) => {
      console.error('Update measure failed:', e)
      notifyError({ title: '更新措施失败' })
    },
  })

  const deleteMeasure = useMutation({
    ...deleteMeasureMutation(),
    onSuccess: invalidateMeasures,
    onError: (e) => {
      console.error('Delete measure failed:', e)
      notifyError({ title: '删除措施失败' })
    },
  })

  async function createMeasureItem(body: MeasureCreate) {
    return createMeasure.mutateAsync({
      path: { project_id: currentProjectId.value! },
      body,
    })
  }

  async function updateMeasureItem(id: number, body: MeasureUpdate) {
    return updateMeasure.mutateAsync({
      path: { project_id: currentProjectId.value!, id },
      body,
    })
  }

  async function deleteMeasureItem(id: number) {
    return deleteMeasure.mutateAsync({
      path: { project_id: currentProjectId.value!, id },
    })
  }

  return {
    // 计划
    plan,
    isLoadingPlan,
    isPlanMissing,
    estimatePlan,
    savePlan,
    savePlanDraft,
    // 措施
    measures,
    isLoadingMeasures,
    createMeasureItem,
    updateMeasureItem,
    deleteMeasureItem,
    // 状态
    isEstimating: estimateMutation.isLoading,
    isSaving: saveMutation.isLoading,
    isSavingDraft: saveDraftMutation.isLoading,
    isMutatingMeasure:
      createMeasure.isLoading.value ||
      updateMeasure.isLoading.value ||
      deleteMeasure.isLoading.value,
    refreshMeasures: measuresQuery.refresh,
    refreshPlan: planQuery.refresh,
  }
}

export type { PlanEstimateRequest, MeasureCreate, MeasureUpdate }
