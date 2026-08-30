import type { AllocationCreateItem, ParsedResourceItem, ResourceMappingCreateItem } from '@/client'
import { useMutation } from '@pinia/colada'
import {
  confirmMappingMutation,
  allocateResourcesMutation,
  submitImportMutation,
} from '@/client/@pinia/colada.gen'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useProjectStorage } from '@/composables/useProjectStorage'
import { useProjectContext } from '@/composables/useProjectContext'

type Phase = 'PENDING' | 'MAPPING' | 'ALLOCATING' | 'COMPLETED'

export const useDailyReportStoreV2 = defineStore('report', () => {
  const { currentProjectId } = useProjectContext()

  // 当前处理阶段
  const currentPhase = useProjectStorage<Phase>('report:current-phase', 'PENDING')

  // 当前步骤索引 (0: import, 1: review, 2: allocate, 3: confirm)
  const currentStepIndex = computed(() => {
    switch (currentPhase.value) {
      case 'PENDING':
        return 0
      case 'MAPPING':
        return 1
      case 'ALLOCATING':
        return 2
      case 'COMPLETED':
        return 3
      default:
        return 0
    }
  })

  // 检查是否可以导航到指定步骤
  const canNavigateToStep = (stepIndex: number): boolean => {
    if (stepIndex <= currentStepIndex.value) return true

    // 检查是否有数据支持导航到后续步骤
    if (stepIndex === 1 && parsedResourceItems.value.length > 0) return true
    if (stepIndex === 2 && currentStepIndex.value == 2) return true
    if (stepIndex === 3 && resourceUsages.value.length > 0) return true

    return false
  }

  // 1. 上传文件进行解析
  const parsedResourceItems = useProjectStorage<ParsedResourceItem[]>(
    'report:parsed-resource-items',
    [],
  )
  const batchId = useProjectStorage('report:batch-id', '')
  // 2. 用户调整解析结果
  // 2.1 默认值
  const defaultMapping = computed<ResourceMappingCreateItem[]>(() => {
    return parsedResourceItems.value.map((item) => ({
      ...item,
      action: item.mappingStatus == 'EXACT_MATCH' ? 'USE_EXISTING' : 'SKIP',
      newResource: null,
    }))
  })
  // 2.2 用户调整的部分
  const mappingChanges = useProjectStorage<ResourceMappingCreateItem[]>(
    'report:mapping-changes',
    [],
  )
  // 2.3 最终发送的值（）
  const mappingDecision = computed<ResourceMappingCreateItem[]>(() => {
    const names = mappingChanges.value.map((item) => item.resourceName)
    return defaultMapping.value.map((item) =>
      names.includes(item.resourceName)
        ? mappingChanges.value.find((i) => i.resourceName == item.resourceName)!
        : item,
    )
  })
  const confirmMappingMute = useMutation(confirmMappingMutation())
  async function confirmMapping() {
    await confirmMappingMute.mutateAsync({
      path: { project_id: currentProjectId.value!, batch_id: batchId.value },
      body: mappingDecision.value,
    })
    currentPhase.value = 'MAPPING'
  }
  // 3. 分配
  // 3.1 已分配的资源 Map<task_id, Map<resource_name, quantity>>
  const allocatedResourceQuantities = useProjectStorage(
    'report:allocated-resource-items',
    new Map() as Map<number, Record<string, number>>,
  )
  // 3.2 展平的资源使用（运输类条目透传 cargo，须与确认映射一致）
  const resourceUsages = computed<AllocationCreateItem[]>(() => {
    const cargoByName = new Map<string, string | null>()
    for (const item of parsedResourceItems.value) {
      cargoByName.set(item.resourceName, item.cargo ?? null)
    }
    const res = []
    for (const [taskId, resourceQuantities] of allocatedResourceQuantities.value.entries()) {
      for (const [resourceName, quantity] of Object.entries(resourceQuantities)) {
        // 后端不接受 quantity 为 0 的资源
        if (quantity != 0)
          res.push({
            taskId,
            resourceName,
            quantity,
            cargo: cargoByName.get(resourceName) ?? null,
          })
      }
    }
    return res
  })
  // 3.3 提交
  const allocateResourcesMute = useMutation(allocateResourcesMutation())
  async function allocateResources() {
    await allocateResourcesMute.mutateAsync({
      path: { project_id: currentProjectId.value!, batch_id: batchId.value },
      body: resourceUsages.value,
    })
    currentPhase.value = 'ALLOCATING'
  }

  // 4. submit
  const submitImportMute = useMutation(submitImportMutation())
  const submitReport = async () => {
    await submitImportMute.mutateAsync({
      path: { project_id: currentProjectId.value!, batch_id: batchId.value },
    })
    currentPhase.value = 'COMPLETED'
  }

  // 5. summary stats
  const summaryStats = computed(() => {
    const totalResources = mappingDecision.value.filter((m) => m.action != 'SKIP').length
    const allocatedTasks = new Set(resourceUsages.value.map((u) => u.taskId)).size
    const totalAllocations = resourceUsages.value.length
    return { totalResources, allocatedTasks, totalAllocations }
  })

  // 6. reset
  const error = ref('')
  function reset() {
    parsedResourceItems.value = []
    batchId.value = ''
    mappingChanges.value = []
    allocatedResourceQuantities.value.clear()
    error.value = ''
    currentPhase.value = 'PENDING'
  }

  return {
    isLoading: computed(
      () =>
        confirmMappingMute.isLoading.value ||
        allocateResourcesMute.isLoading.value ||
        submitImportMute.isLoading.value,
    ),
    currentPhase,
    currentStepIndex,
    canNavigateToStep,
    parsedResourceItems,
    batchId,
    mappingDecision,
    mappingChanges,
    confirmMapping,
    allocatedResourceQuantities,
    resourceUsages,
    allocateResources,
    submitReport,
    summaryStats,
    reset,
    error,
  }
})
