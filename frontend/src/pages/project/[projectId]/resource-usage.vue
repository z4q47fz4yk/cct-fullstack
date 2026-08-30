<script setup lang="ts">
/**
 * 资源使用录入主页
 * - 顶级导航（navOrder: 3）
 * - 三个 tab：录入 / 历史 / 统计
 * - 录入 tab 基于后端 batch 接口（POST /projects/{id}/resource-usage/batch）
 */
import { computed, onMounted, ref, watch } from 'vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ResourceUsageEntryTabs from '@/components/resource-usage/ResourceUsageEntryTabs.vue'
import ResourceUsageEntryTable, {
  type PendingUsageRow,
} from '@/components/resource-usage/ResourceUsageEntryTable.vue'
import ResourceUsageBatchList from '@/components/resource-usage/ResourceUsageBatchList.vue'
import ResourceUsageBatchDetail from '@/components/resource-usage/ResourceUsageBatchDetail.vue'
import ResourceUsageFilters from '@/components/resource-usage/ResourceUsageFilters.vue'
import ResourceUsageChart from '@/components/resource-usage/ResourceUsageChart.vue'
import ResourceUsageChartFilters from '@/components/resource-usage/ResourceUsageChartFilters.vue'
import TagAssignModal from '@/components/tag/TagAssignModal.vue'
import {
  useResourceUsageApi,
  useResourceUsagesByDate,
  type ResourceUsageFilters as Filters,
} from '@/composables/useResourceUsageApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'

import { useUsageTypeToggle } from '@/composables/useUsageTypeToggle'
import type { TagEntityRef } from '@/composables/useEntityTagApi'
import type {
  ResourceUsageBatchCreate,
  ResourceUsageBatchItem,
  ResourceUsageResp,
  ResourceUsageUpdate,
  ResourceUsageWithTagsResp,
  TagResp,
} from '@/client/types.gen'
import type { ResourceResp } from '@/client/types.gen'
import { ApiError, formatHttpError } from '@/utils/error'
import { todayIsoLocal } from '@/utils/date'

definePage({
  meta: {
    title: '资源使用录入',
    description: '手动录入、查看与统计资源使用量',
    icon: 'edit_note',
    showInNav: true,
    navOrder: 3,
  },
})

type TabKey = 'entry' | 'history' | 'statistics'
const activeTab = ref<TabKey>('entry')

// 项目 ID
const { currentProjectId } = useProjectContext()

// 当前 tab 共享的「日期」——录入 tab 顶部 + 历史 tab 详情展示
// 本地时区“今天”（toISOString 为 UTC，跨时区会取到昨天）
const todayIso = todayIsoLocal
const usageDate = ref(todayIso())

// 录入 tab 的待提交行（前端临时态）
const pendingRows = ref<PendingUsageRow[]>([])

// 提交结果错误信息（行级 + 总览）
const submitErrorMessage = ref('')
const submitting = ref(false)

// 历史 tab 状态
const filters = ref<Filters>({})
const historyPage = ref(1)
const historyPageSize = ref(20)

const {
  usages,
  totalCount: _totalCount,
  isLoading,
  error,
  refresh,
  createUsageBatch,
  updateUsage,
  deleteUsage,
  deleteBatch,
} = useResourceUsageApi({
  filters,
  page: historyPage,
  pageSize: historyPageSize,
})

// 当前正在查看详情的 batch 复合 key
const viewingBatchKey = ref<string | number | null>(null)
const viewingBatchRecords = computed<ResourceUsageResp[]>(() => {
  if (viewingBatchKey.value === null) return []
  return usages.value.filter((u) => {
    const rawId = u.manualBatchId ?? u.batchId ?? null
    return rawId !== null && String(rawId) === String(viewingBatchKey.value)
  })
})

function openBatchDetail(key: string | number) {
  viewingBatchKey.value = key
}
function closeBatchDetail() {
  viewingBatchKey.value = null
}

// ─── 录入 tab 操作 ──────────────────────────────────────────

function handleAddRow(row: Omit<PendingUsageRow, '_key' | 'error'>) {
  pendingRows.value.push({
    _key: crypto.randomUUID(),
    ...row,
  })
}
function handleUpdateRow(key: string, row: Omit<PendingUsageRow, '_key' | 'error'>) {
  const idx = pendingRows.value.findIndex((r) => r._key === key)
  if (idx >= 0) {
    pendingRows.value[idx] = { _key: key, ...row }
  }
}
function handleRemoveRow(key: string) {
  pendingRows.value = pendingRows.value.filter((r) => r._key !== key)
}
function handleClearRows() {
  pendingRows.value = []
  submitErrorMessage.value = ''
}

// ─── 当天已有记录预检 ──────────────────────────────────────────
const { records: existingRecords, refresh: refreshExisting } = useResourceUsagesByDate(usageDate)

// key = `${task_id}|${resource_id}`
const existingDuplicateKeys = computed<Set<string>>(() => {
  const set = new Set<string>()
  for (const r of existingRecords.value) {
    set.add(`${r.taskId}|${r.resourceId}`)
  }
  return set
})
const pendingRowDuplicateKeys = computed<Set<string>>(() => {
  const set = new Set<string>()
  for (const r of pendingRows.value) {
    if (existingDuplicateKeys.value.has(`${r.task_id}|${r.resource_id}`)) {
      set.add(r._key)
    }
  }
  return set
})
const hasBlockingDuplicate = computed(() => pendingRowDuplicateKeys.value.size > 0)

// 当用户切换日期时，重新拉取当日已有记录（query 通过 ref 触发自动刷新）
watch(usageDate, () => {
  // useResourceUsagesByDate 通过 ref 触发，可手动 invalidate
  refreshExisting()
  // 默认 label 同步
  if (/^手动录入( - \d{4}-\d{2}-\d{2})?$/.test(batchLabel.value)) {
    resetLabel()
  }
})

async function handleSubmit(payload: {
  rows: Omit<PendingUsageRow, '_key' | 'error'>[]
  usageDate: string
}) {
  if (payload.rows.length === 0) return
  // 二次防御：极端并发下可能仍有冲突
  const conflicting = payload.rows.filter((r) =>
    existingDuplicateKeys.value.has(`${r.task_id}|${r.resource_id}`),
  )
  if (conflicting.length > 0) {
    submitErrorMessage.value = '部分行与当日已存在的记录冲突，请移除后再提交'
    return
  }
  submitting.value = true
  submitErrorMessage.value = ''
  try {
    const items: ResourceUsageBatchItem[] = payload.rows.map((r) => ({
      task_id: r.task_id,
      resource_id: r.resource_id,
      usage_date: payload.usageDate,
      quantity: r.quantity,
      usage_type: usageType.value,
    }))
    const body: ResourceUsageBatchCreate = {
      name: batchLabel.value.trim() || `手动录入 - ${payload.usageDate}`,
      items,
    }
    await createUsageBatch({
      path: { project_id: currentProjectId.value! },
      body,
    })
    // 成功后清空
    pendingRows.value = []
    submitErrorMessage.value = ''
    // 重新生成新 label（保留用户输入的前缀也可，但默认重置避免误用旧 label）
    resetLabel()
    // 刷新历史 + 当天已有记录
    await Promise.all([refresh(), refreshExisting()])
  } catch (e) {
    const err = e as ApiError
    if (err?.status === 409) {
      submitErrorMessage.value =
        '提交失败：当日已存在相同的工序与资源组合（同 batch API 返回 409）。请检查或稍后重试。'
    } else if (err?.status === 422) {
      submitErrorMessage.value =
        '提交失败：存在无效的工序或资源引用（同 batch API 返回 422）。请检查后再试。'
    } else {
      submitErrorMessage.value = `提交失败：${formatHttpError(err, '未知错误')}`
    }
  } finally {
    submitting.value = false
  }
}

// ─── 历史 tab 操作 ──────────────────────────────────────────

async function handleDeleteRecord(id: number) {
  try {
    await deleteUsage({ path: { project_id: currentProjectId.value!, id } })
    await refresh()
    if (viewingBatchKey.value !== null && viewingBatchRecords.value.length === 0) {
      closeBatchDetail()
    }
  } catch (e) {
    console.error('Delete record failed:', e)
  }
}

async function handleUpdateRecord(id: number, data: ResourceUsageUpdate) {
  try {
    await updateUsage({ path: { project_id: currentProjectId.value!, id }, body: data })
    await refresh()
  } catch (e) {
    console.error('Update record failed:', e)
  }
}

async function handleDeleteBatch(_key: string | number, records: ResourceUsageResp[]) {
  try {
    await deleteBatch(records)
    if (viewingBatchKey.value === _key) closeBatchDetail()
    await refresh()
  } catch (e) {
    console.error('Delete batch failed:', e)
  }
}

// ─── 用量打标（USAGE 切片实体，导入后的用量也可补标） ──────
const showUsageTagModal = ref(false)
const taggingUsage = ref<ResourceUsageResp | null>(null)
const taggingUsageName = computed(() => {
  if (!taggingUsage.value) return '用量'
  return `用量 #${taggingUsage.value.id}`
})

function openUsageTags(usage: ResourceUsageResp) {
  taggingUsage.value = usage
  showUsageTagModal.value = true
}

// ─── 批次打标（整批记录应用同一组标签） ─────────────────────
const showBatchTagModal = ref(false)
const taggingBatchRecords = ref<ResourceUsageWithTagsResp[]>([])

function openBatchTags(records: ResourceUsageWithTagsResp[]) {
  taggingBatchRecords.value = records
  showBatchTagModal.value = true
}

const taggingBatchName = computed(() => {
  const count = taggingBatchRecords.value.length
  return count > 0 ? `用量批次（${count} 条记录）` : '用量批次'
})

/** 批量打标目标实体：批次内每条记录 */
const taggingBatchEntities = computed<TagEntityRef[]>(() =>
  taggingBatchRecords.value.map((r) => ({ type: 'usage', id: r.id })),
)

/** 批量模式初始标签：批次内所有记录当前标签的并集 */
const taggingBatchInitialTags = computed<TagResp[]>(() => {
  const map = new Map<number, TagResp>()
  for (const r of taggingBatchRecords.value) {
    for (const t of r.tags ?? []) {
      if (!map.has(t.id)) map.set(t.id, t)
    }
  }
  return Array.from(map.values())
})

// ─── 统计 tab ──────────────────────────────────────────────
const selectedResourceIds = ref<number[]>([])

// 拉取所有资源（按 category 列表做全集）
const { state: allResourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: FETCH_ALL_PAGE_SIZE },
  }),
)
const allResources = computed<ResourceResp[]>(() => allResourcesState.value?.data?.items ?? [])
const chartResources = computed<ResourceResp[]>(() =>
  allResources.value.filter((r) => selectedResourceIds.value.includes(r.id)),
)

// 初始化：默认选前 5 个资源
onMounted(() => {
  if (selectedResourceIds.value.length === 0 && allResources.value.length > 0) {
    selectedResourceIds.value = allResources.value.slice(0, 5).map((r) => r.id)
  }
})

// 切换 tab 时清空错误
function setTab(t: TabKey) {
  activeTab.value = t
  submitErrorMessage.value = ''
  if (t === 'history') closeBatchDetail()
}

// 批次名称（可编辑标签）
const defaultLabel = computed(() => `手动录入 - ${usageDate.value}`)
const batchLabel = ref(defaultLabel.value)
function resetLabel() {
  batchLabel.value = defaultLabel.value
}

// 用量类型切换（实际 / 计划）
const { usageType } = useUsageTypeToggle()

// 总览：当日已有记录数
const existingCount = computed(() => existingRecords.value.length)
</script>

<template>
  <Teleport defer to="#header-actions">
    <ResourceUsageEntryTabs v-model:active-tab="activeTab" @update:active-tab="setTab" />
  </Teleport>

  <ErrorState
    v-if="error && activeTab === 'history'"
    title="加载失败"
    description="无法获取使用量记录，请检查网络连接"
    class="mb-4"
    @retry="refresh"
  />

  <!-- 录入 tab -->
  <div v-show="activeTab === 'entry'">
    <ResourceUsageEntryTable
      v-model:usageDate="usageDate"
      v-model:usageType="usageType"
      v-model:batchLabel="batchLabel"
      :existing-count="existingCount"
      :rows="pendingRows"
      :submit-error-message="submitErrorMessage"
      :existing-duplicate-keys="pendingRowDuplicateKeys"
      @add-row="handleAddRow"
      @update-row="handleUpdateRow"
      @remove-row="handleRemoveRow"
      @clear-rows="handleClearRows"
      @submit="handleSubmit"
    />
  </div>

  <!-- 历史 tab -->
  <div v-show="activeTab === 'history'">
    <ResourceUsageFilters v-model:filters="filters" />

    <ResourceUsageBatchList
      class="panel p-0"
      v-if="viewingBatchKey === null"
      :usages="usages"
      :loading="isLoading"
      @view-detail="openBatchDetail"
      @delete-batch="handleDeleteBatch"
      @tags-batch="openBatchTags"
    />

    <ResourceUsageBatchDetail
      v-else
      :batch-key="viewingBatchKey"
      :records="viewingBatchRecords"
      :loading="isLoading"
      @close="closeBatchDetail"
      @update-record="handleUpdateRecord"
      @delete-record="handleDeleteRecord"
      @delete-batch="handleDeleteBatch(viewingBatchKey!, viewingBatchRecords)"
      @tags="openUsageTags"
    />
  </div>

  <!-- 统计 tab -->
  <div v-show="activeTab === 'statistics'">
    <ResourceUsageChartFilters v-model:selected-resource-ids="selectedResourceIds" />
    <ResourceUsageChart :resources="chartResources" />
  </div>

  <!-- 用量打标模态框 -->
  <TagAssignModal
    :show="showUsageTagModal"
    :entity="taggingUsage ? { type: 'usage', id: taggingUsage.id } : null"
    :entity-name="taggingUsageName"
    @saved="showUsageTagModal = false"
    @cancel="showUsageTagModal = false"
  />

  <!-- 批次打标模态框 -->
  <TagAssignModal
    :show="showBatchTagModal"
    :entity="null"
    :entities="taggingBatchEntities"
    :initial-tags="taggingBatchInitialTags"
    :entity-name="taggingBatchName"
    @saved="showBatchTagModal = false"
    @cancel="showBatchTagModal = false"
  />
</template>
