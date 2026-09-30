<script setup lang="ts">
/**
 * 资源使用量 - 录入（手动/日报统一入口）
 *
 * - 顶部工具栏：使用日期 + 口径徽标 + 从日报导入（仅实际口径可用）
 * - info 横幅栏：推断原因 + 强制复选框（强制时 warning 色）
 * - 统一「待提交数据」卡片（UsageEntrySummary）：日报（实线）+ 手动（虚线）徽标并排
 * - 当日工序进度（可选）+ 一键「完成一天的录入」
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMutation } from '@pinia/colada'
import UsageEntrySummary, {
  type PendingUsageRow,
} from '@/components/resource-usage/UsageEntrySummary.vue'
import { useResourceUsagesByDate } from '@/composables/useResourceUsageApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useUsageDateType } from '@/composables/useUsageDateType'
import { useDailyReportStoreV2 } from '@/stores/report'
import { useProgressApi } from '@/composables/useProgressApi'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useToast } from '@/composables/useToast'
import { batchCreateResourceUsageMutation } from '@/client/@pinia/colada.gen'

import type {
  ResourceUsageBatchCreate,
  ResourceUsageBatchItem,
  TaskProgressBatchItem,
} from '@/client/types.gen'
import { ApiError, formatHttpError } from '@/utils/error'

definePage({
  meta: {
    title: '录入',
    description: '手动/日报统一录入入口',
    icon: 'edit_note',
    showInNav: true,
    parentName: '/project/[projectId]/resource-usage',
    navOrder: 2,
  },
})

const { currentProjectId } = useProjectContext()

// 共享日期 + 用量类型推断（手动与日报共用）
const { usageDate, effectiveUsageType, inferenceReason, isForced, forceToggle, forceLabel } =
  useUsageDateType()

// 手动待提交行
const pendingRows = ref<PendingUsageRow[]>([])
// 手动参与的工序集合（含尚无手动行的「待分配工序」）
const manualTaskIds = ref<number[]>([])

function handleAddTask(taskId: number) {
  if (!manualTaskIds.value.includes(taskId)) manualTaskIds.value.push(taskId)
}

// 提交结果错误信息
const submitErrorMessage = ref('')
const submitting = ref(false)

// ─── 手动行操作 ──────────────────────────────────────────

function handleAddRow(row: Omit<PendingUsageRow, '_key' | 'error'>) {
  pendingRows.value.push({ _key: crypto.randomUUID(), ...row })
  if (!manualTaskIds.value.includes(row.task_id)) manualTaskIds.value.push(row.task_id)
}
function handleUpdateRow(key: string, row: Omit<PendingUsageRow, '_key' | 'error'>) {
  const idx = pendingRows.value.findIndex((r) => r._key === key)
  if (idx >= 0) pendingRows.value[idx] = { _key: key, ...row }
}
function handleRemoveRow(key: string) {
  pendingRows.value = pendingRows.value.filter((r) => r._key !== key)
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

// 当用户切换日期时，重新拉取当日已有记录
watch(usageDate, () => {
  refreshExisting()
})

// ─── 日报批次（待提交） ────────────────────────────────────
const reportStore = useDailyReportStoreV2()
const hasPendingReportBatch = computed(
  () => !!reportStore.batchId && reportStore.resourceUsages.length > 0,
)

// ─── 当日工序进度（可选，随「完成一天录入」提交） ────────────
const { recordProgressBatch, isRecording } = useProgressApi()
const progressEntries = ref<Record<number, number>>({})

// 涉及工序 = 手动行工序 ∪ 待分配工序 ∪ 日报批次工序
const involvedTaskIds = computed<number[]>(() => {
  const set = new Set<number>()
  for (const r of pendingRows.value) set.add(r.task_id)
  for (const id of manualTaskIds.value) set.add(id)
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

/** 当前本地时间（HH:mm），用于批次备注区分同日多批次（M-10/E-8） */
function nowHmLocal(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function handleCompleteDay() {
  // 防重复提交：提交中忽略再次触发（E-10，配合粘性操作条单按钮实例）
  if (submitting.value || isRecording.value) return

  const manualRows = pendingRows.value.filter((r) => !pendingRowDuplicateKeys.value.has(r._key))
  if (
    manualRows.length === 0 &&
    !hasPendingReportBatch.value &&
    Object.keys(progressEntries.value).length === 0
  ) {
    notifyError({ title: '没有可提交的内容', description: '请先补充手动用量、导入日报或填写进度' })
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

  // 提交前缓存涉及工序（日报 submit 成功后 store.reset() 会清空 resourceUsages）
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
        // 备注带提交时刻（HH:mm），同日多批次可区分（M-10/E-8）
        name: `手动录入 - ${usageDate.value} ${nowHmLocal()}`,
        items,
      }
      try {
        await createUsageBatchLocal({
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

    // 2. 待提交日报批次 → submit（恒 ACTUAL，不受口径/强制影响）
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
      progressEntries.value = {}
      // 成功提交后重置待分配工序（重新开始新一天的录入）
      manualTaskIds.value = []
    }
    if (failed) {
      notifyError({ title: '部分提交失败', description: '失败项已保留，请处理后重试' })
    }

    // 刷新当天已有记录
    await refreshExisting()
  } finally {
    submitting.value = false
  }
}

// 手动 batch 提交（独立 useMutation，避免与历史页共享实例的耦合）
const { mutateAsync: createUsageBatchLocal } = useMutation({
  ...batchCreateResourceUsageMutation(),
})

// ─── 日报导入入口（仅实际口径可用） ─────────────────────────
const router = useRouter()
function gotoDailyReportImport() {
  if (effectiveUsageType.value !== 'ACTUAL') return
  const id = currentProjectId.value
  if (id == null) return
  router.push(`/project/${id}/daily-report/import`)
}

// ─── 总览：当日已有记录数（同口径） ─────────────────────────
const existingCount = computed(() => existingRecords.value.length)

const typeBadgeClass = computed(() =>
  effectiveUsageType.value === 'ACTUAL' ? 'badge-success' : 'badge-neutral',
)
const typeBadgeLabel = computed(() => (effectiveUsageType.value === 'ACTUAL' ? '实际' : '计划'))

// info 栏取色：强制时 warning，未强制时 info
const infoTone = computed(() => (isForced.value ? 'warning' : 'info'))
</script>

<template>
  <!-- 顶部工具栏：日期 + 口径 + 从日报导入 -->
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

      <span class="badge badge-sm" :class="typeBadgeClass">{{ typeBadgeLabel }}口径</span>

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

    <!-- info 栏：推断原因 + 强制复选框（强制时 warning） -->
    <div
      class="px-5 py-3 flex flex-wrap items-center gap-3"
      :class="infoTone === 'warning' ? 'bg-warning/10' : 'bg-info/10'"
    >
      <span
        class="material-symbols-outlined icon-sm"
        :class="infoTone === 'warning' ? 'text-warning' : 'text-info'"
      >
        info
      </span>
      <span class="text-sm text-base-content/80">{{ inferenceReason }}</span>
      <label class="flex items-center gap-1 text-sm text-base-content/70 cursor-pointer">
        <input
          type="checkbox"
          class="checkbox checkbox-sm"
          :checked="isForced"
          @change="forceToggle"
        />
        {{ forceLabel }}
      </label>
      <span v-if="effectiveUsageType === 'PLANNED'" class="text-xs text-fg-muted">
        （计划口径下不支持从日报导入）
      </span>
    </div>
  </div>

  <!-- 统一「待提交数据」卡片 -->
  <UsageEntrySummary
    v-model:manual-rows="pendingRows"
    v-model:manual-task-ids="manualTaskIds"
    :usage-date="usageDate"
    :usage-type="effectiveUsageType"
    :existing-duplicate-keys="pendingRowDuplicateKeys"
    @add-row="handleAddRow"
    @update-row="handleUpdateRow"
    @remove-row="handleRemoveRow"
    @remove-batch="reportStore.reset()"
    @add-task="handleAddTask"
  />

  <!-- 当日工序进度（可选，随「完成一天的录入」提交） -->
  <div class="panel p-4 mt-4">
    <div class="flex items-center justify-between mb-1">
      <h3 class="text-sm font-semibold text-base-content">当日工序进度（可选）</h3>
      <span class="text-xs text-fg-subtle font-mono">{{ usageDate }}</span>
    </div>
    <p class="text-xs text-fg-subtle mb-3">
      为涉及工序录入当日完成百分比（0-100），进度到 100% 即判定该工序完成；留空则不更新
    </p>
    <div v-if="involvedTaskIds.length === 0" class="text-sm text-fg-muted py-2">
      暂无涉及工序（先补充手动用量或导入日报）
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

  <div v-if="submitErrorMessage" class="alert alert-error alert-sm mt-4" role="alert">
    <span class="material-symbols-outlined icon-sm">error</span>
    <span class="text-sm">{{ submitErrorMessage }}</span>
  </div>

  <!-- 粘性底部操作条：小视口（如 1280×633）下提交入口始终可达（E-10）；
       仅保留这一个提交按钮实例，提交中禁用 + 入口防重入，不会重复提交 -->
  <div class="sticky bottom-0 z-10 mt-4 border-t border-base-content/10 bg-base-100 px-4 pb-4 pt-3">
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
</template>
