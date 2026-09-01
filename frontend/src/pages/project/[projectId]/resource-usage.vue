<script setup lang="ts">
/**
 * 资源使用量主页
 * - 顶级导航（navOrder: 3）
 * - 三个 tab：历史（默认主视图）/ 录入 / 统计
 * - 顶部共享工具栏：页面级唯一日期 + 用量类型推断（按实际开工日）+ 强制切换 + 从日报导入
 * - 录入 tab：手动录入（按工序汇总）+ 待提交日报批次 + 当日工序进度 + 一键「完成一天的录入」
 * - 历史 tab 展示全部来源（手动/日报）批次，带用量类型徽标
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ErrorState from '@/components/common/ErrorState.vue'
import ResourceUsageEntryTabs from '@/components/resource-usage/ResourceUsageEntryTabs.vue'
import ManualUsageByTask, {
  type PendingUsageRow,
} from '@/components/resource-usage/ManualUsageByTask.vue'
import DailyReportBatchCard from '@/components/resource-usage/DailyReportBatchCard.vue'
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
import { useUsageDateType } from '@/composables/useUsageDateType'
import { useDailyReportStoreV2 } from '@/stores/report'
import { useProgressApi } from '@/composables/useProgressApi'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useToast } from '@/composables/useToast'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'

import type { TagEntityRef } from '@/composables/useEntityTagApi'
import type {
  ResourceUsageBatchCreate,
  ResourceUsageBatchItem,
  ResourceUsageResp,
  ResourceUsageUpdate,
  ResourceUsageWithTagsResp,
  TagResp,
  TaskProgressBatchItem,
} from '@/client/types.gen'
import type { ResourceResp } from '@/client/types.gen'
import { ApiError, formatHttpError } from '@/utils/error'

definePage({
  meta: {
    title: '资源使用量',
    description: '录入、查看与统计资源使用量（手动/日报统一入口）',
    icon: 'inventory_2',
    showInNav: true,
    navOrder: 3,
  },
})

type TabKey = 'history' | 'entry' | 'statistics'
const route = useRoute()
// 默认主视图为「历史」；支持 ?tab=entry（日报向导分配完成后跳回录入）
const activeTab = ref<TabKey>((route.query.tab as TabKey) || 'history')

// 项目 ID
const { currentProjectId } = useProjectContext()

// 共享日期 + 用量类型推断（手动与日报共用）
const { usageDate, effectiveUsageType, inferenceReason, isForced, forceToggle, forceLabel } =
  useUsageDateType()

// 手动录入的待提交行（前端临时态，按工序汇总）
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

// ─── 手动行操作 ──────────────────────────────────────────

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

// ─── 当天已有记录预检（按有效口径过滤） ──────────────────────
const { records: existingRecords, refresh: refreshExisting } = useResourceUsagesByDate(
  usageDate,
  effectiveUsageType,
)

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
  refreshExisting()
})

// ─── 日报批次（待提交） ────────────────────────────────────
const reportStore = useDailyReportStoreV2()
const hasPendingReportBatch = computed(
  () => !!reportStore.batchId && reportStore.resourceUsages.length > 0,
)
// 日报批次涉及的工序 id（供「全手动工序」徽标判断）
const reportTaskIds = computed<number[]>(() =>
  Array.from(new Set(reportStore.resourceUsages.map((u) => u.taskId))),
)

// ─── 当日工序进度（可选，随「完成一天录入」提交） ────────────
const { recordProgressBatch, isRecording } = useProgressApi()
const progressEntries = ref<Record<number, number>>({})

// 涉及工序 = 手动行工序 ∪ 日报批次工序
const involvedTaskIds = computed<number[]>(() => {
  const set = new Set<number>()
  for (const r of pendingRows.value) set.add(r.task_id)
  for (const u of reportStore.resourceUsages) set.add(u.taskId)
  return Array.from(set)
})

function progressValue(taskId: number): string {
  const v = progressEntries.value[taskId]
  return v === undefined || v === null ? '' : String(v)
}

function setProgressValue(taskId: number, raw: string) {
  const n = Number(raw)
  progressEntries.value[taskId] = Number.isNaN(n) ? 0 : Math.min(Math.max(n, 0), 100)
}

// 工序名展示（供进度块）
const { tasks: scheduleTasks } = useScheduleApi()
const taskById = computed(() => new Map((scheduleTasks.value ?? []).map((t) => [t.id, t])))

// ─── 统一提交：完成一天的录入 ──────────────────────────────
const { notifySuccess, notifyError } = useToast()

async function handleCompleteDay() {
  const manualRows = pendingRows.value.filter((r) => !pendingRowDuplicateKeys.value.has(r._key))
  if (
    manualRows.length === 0 &&
    !hasPendingReportBatch.value &&
    Object.keys(progressEntries.value).length === 0
  ) {
    notifyError({ title: '没有可提交的内容', description: '请先录入手动用量、导入日报或填写进度' })
    return
  }
  if (hasBlockingDuplicate.value) {
    submitErrorMessage.value = '部分行与当日已存在的记录冲突，请移除后再提交'
    return
  }

  submitting.value = true
  submitErrorMessage.value = ''
  const results: string[] = []
  let failed = false

  // 提交前缓存涉及工序（日报 submit 成功后 store.reset() 会清空 resourceUsages，
  // 进度收集必须用提交前的快照）
  const involvedTaskIdsSnapshot = Array.from(involvedTaskIds.value)

  try {
    // 1. 手动行 → batch 提交
    if (manualRows.length > 0) {
      const items: ResourceUsageBatchItem[] = manualRows.map((r) => ({
        task_id: r.task_id,
        resource_id: r.resource_id,
        usage_date: usageDate.value,
        quantity: r.quantity,
        usage_type: effectiveUsageType.value,
      }))
      const body: ResourceUsageBatchCreate = {
        name: `手动录入 - ${usageDate.value}`,
        items,
      }
      try {
        await createUsageBatch({
          path: { project_id: currentProjectId.value! },
          body,
        })
        results.push(`手动 ${manualRows.length} 条`)
        pendingRows.value = []
      } catch (e) {
        failed = true
        const err = e as ApiError
        if (err?.status === 409) {
          submitErrorMessage.value =
            '手动用量提交失败：当日已存在相同的工序与资源组合（同口径）。请检查或稍后重试。'
        } else if (err?.status === 422) {
          submitErrorMessage.value = '手动用量提交失败：存在无效的工序或资源引用。请检查后再试。'
        } else {
          submitErrorMessage.value = `手动用量提交失败：${formatHttpError(err, '未知错误')}`
        }
      }
    }

    // 2. 待提交日报批次 → submit（恒 ACTUAL）
    if (hasPendingReportBatch.value) {
      try {
        await reportStore.submitReport()
        results.push('日报 1 批')
        reportStore.reset()
      } catch (e) {
        failed = true
        const err = e as ApiError
        if (err?.status === 409) {
          submitErrorMessage.value = `日报提交失败：${formatHttpError(err, '与现有记录冲突')}`
        } else {
          submitErrorMessage.value = `日报提交失败：${formatHttpError(err, '未知错误')}`
        }
      }
    }

    // 3. 当日工序进度（用户填写了才发）
    const progressItems: TaskProgressBatchItem[] = []
    for (const tid of involvedTaskIdsSnapshot) {
      const percent = progressEntries.value[tid] ?? 0
      if (percent > 0) progressItems.push({ task_id: tid, date: usageDate.value, percent })
    }
    if (progressItems.length > 0) {
      try {
        await recordProgressBatch(progressItems)
        results.push(`进度 ${progressItems.length} 项`)
      } catch (e) {
        failed = true
        console.error('Submit progress failed:', e)
        submitErrorMessage.value = '进度提交失败，可稍后在任务管理中补录。'
      }
    }

    // 4. 汇总反馈
    if (results.length > 0) {
      notifySuccess({ title: '已完成一天的录入', description: `已提交：${results.join('、')}` })
      // 成功提交后清空进度草稿（避免同日重复提交）
      progressEntries.value = {}
    }
    if (failed) {
      notifyError({ title: '部分提交失败', description: '失败项已保留，请处理后重试' })
    }

    // 刷新历史 + 当天已有记录
    await Promise.all([refresh(), refreshExisting()])
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

// 日报导入入口（仅实际口径可用）
const router = useRouter()
function gotoDailyReportImport() {
  if (effectiveUsageType.value !== 'ACTUAL') return
  const id = currentProjectId.value
  if (id == null) return
  router.push(`/project/${id}/daily-report/import`)
}

// ─── 总览：当日已有记录数（同口径） ─────────────────────────
const existingCount = computed(() => existingRecords.value.length)

// 是否有强制标记
const typeBadgeClass = computed(() =>
  effectiveUsageType.value === 'ACTUAL' ? 'badge-success' : 'badge-warning',
)
const typeBadgeLabel = computed(() => (effectiveUsageType.value === 'ACTUAL' ? '实际' : '计划'))
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

  <!-- 顶部共享工具栏：日期 + 类型推断 + 强制切换 + 日报导入 -->
  <div class="p-4 panel mb-4">
    <div class="px-5 py-4 border-b border-base-content/10 flex flex-wrap items-center gap-4">
      <div class="flex items-center gap-2">
        <label class="text-sm text-base-content/70 whitespace-nowrap">使用日期：</label>
        <input
          type="date"
          :value="usageDate"
          class="input h-9 text-sm"
          @change="(e) => (usageDate = (e.target as HTMLInputElement).value)"
        />
      </div>

      <div class="flex items-center gap-2">
        <span class="badge badge-sm" :class="typeBadgeClass"> {{ typeBadgeLabel }}口径 </span>
        <label class="flex items-center gap-1 text-sm text-base-content/70 cursor-pointer">
          <input
            type="checkbox"
            class="checkbox checkbox-sm"
            :checked="isForced"
            @change="forceToggle"
          />
          {{ forceLabel }}
        </label>
      </div>

      <div class="flex items-center gap-2 ml-auto">
        <span class="badge badge-sm badge-neutral">
          当日已有 {{ existingCount }} 条（{{ typeBadgeLabel }}）
        </span>
        <button
          type="button"
          class="btn btn-ghost btn-sm gap-1"
          :disabled="effectiveUsageType !== 'ACTUAL'"
          :title="effectiveUsageType !== 'ACTUAL' ? '计划口径下不支持日报导入' : '从日报导入'"
          @click="gotoDailyReportImport"
        >
          <span class="material-symbols-outlined icon-sm">upload_file</span>
          从日报导入
        </button>
      </div>
    </div>

    <div
      class="px-5 py-3 flex flex-wrap items-center gap-3"
      :class="effectiveUsageType === 'PLANNED' ? 'bg-warning/10' : 'bg-info/10'"
    >
      <span
        class="material-symbols-outlined icon-sm"
        :class="effectiveUsageType === 'PLANNED' ? 'text-warning' : 'text-info'"
      >
        info
      </span>
      <span class="text-sm text-base-content/80">{{ inferenceReason }}</span>
      <span v-if="effectiveUsageType === 'PLANNED'" class="text-xs text-fg-muted">
        （计划口径下不支持从日报导入）
      </span>
    </div>
  </div>

  <!-- 历史 tab（默认主视图） -->
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

  <!-- 录入 tab -->
  <div v-show="activeTab === 'entry'" class="space-y-4">
    <!-- 待提交日报批次（只读汇总 + 移除） -->
    <DailyReportBatchCard v-if="hasPendingReportBatch" />

    <!-- 手动录入（按工序汇总，可编辑） -->
    <ManualUsageByTask
      :rows="pendingRows"
      :usage-date="usageDate"
      :usage-type="effectiveUsageType"
      :report-task-ids="reportTaskIds"
      :existing-duplicate-keys="pendingRowDuplicateKeys"
      @add-row="handleAddRow"
      @update-row="handleUpdateRow"
      @remove-row="handleRemoveRow"
      @clear-rows="handleClearRows"
    />

    <!-- 当日工序进度（可选，随「完成一天的录入」提交） -->
    <div class="panel p-4">
      <div class="flex items-center justify-between mb-1">
        <h3 class="text-sm font-semibold text-base-content">当日工序进度（可选）</h3>
        <span class="text-xs text-fg-subtle font-mono">{{ usageDate }}</span>
      </div>
      <p class="text-xs text-fg-subtle mb-3">
        为涉及工序录入当日完成百分比（0-100），进度到 100% 即判定该工序完成；留空则不更新
      </p>
      <div v-if="involvedTaskIds.length === 0" class="text-sm text-fg-muted py-2">
        暂无涉及工序（先录入手动用量或导入日报）
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div
          v-for="tid in involvedTaskIds"
          :key="tid"
          class="flex items-center gap-3 rounded-lg border border-base-content/10 px-3 py-2"
        >
          <div class="flex-1 min-w-0">
            <p class="text-sm text-base-content truncate">
              {{ taskById.get(tid)?.code }} {{ taskById.get(tid)?.name ?? `工序 #${tid}` }}
            </p>
          </div>
          <label class="input input-xs input-bordered w-28 flex items-center gap-1">
            <input
              type="number"
              min="0"
              max="100"
              step="5"
              class="w-full bg-transparent outline-none font-num"
              :value="progressValue(tid)"
              placeholder="0-100"
              @input="setProgressValue(tid, ($event.target as HTMLInputElement).value)"
            />
            <span class="text-xs text-fg-subtle">%</span>
          </label>
        </div>
      </div>
    </div>

    <div v-if="submitErrorMessage" class="alert alert-error alert-sm" role="alert">
      <span class="material-symbols-outlined icon-sm">error</span>
      <span class="text-sm">{{ submitErrorMessage }}</span>
    </div>

    <div class="pt-2">
      <button
        class="btn btn-primary btn-block"
        :disabled="
          submitting ||
          isRecording ||
          (pendingRows.length === 0 && !hasPendingReportBatch && involvedTaskIds.length === 0)
        "
        @click="handleCompleteDay"
      >
        <span v-if="submitting || isRecording" class="loading loading-spinner loading-xs"></span>
        <span v-else class="material-symbols-outlined">rocket_launch</span>
        <span>
          {{
            submitting || isRecording
              ? '提交中...'
              : `完成一天的录入${hasPendingReportBatch ? '（含日报批次）' : ''}`
          }}
        </span>
      </button>
    </div>
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
