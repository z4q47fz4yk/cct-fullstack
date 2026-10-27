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
    showInNav: false,
    parentName: '/project/[projectId]/resource-usage',
    navOrder: 2,
  },
})

/**
 * 固定口径（计划/实际数据录入两个菜单入口共用本页）：
 * - null（直接访问本路由）→ 保持原行为：按日期自动推断 + 可强制切换
 * - 'PLANNED' / 'ACTUAL' → 入口页固定口径，隐藏强制切换
 */
const { pinnedType = null } = defineProps<{
  pinnedType?: 'PLANNED' | 'ACTUAL' | null
}>()

const { currentProjectId } = useProjectContext()

// 共享日期 + 用量类型推断（手动与日报共用）
const { usageDate, effectiveUsageType: inferredType, inferenceReason, isForced, forceToggle, forceLabel } =
  useUsageDateType()

// 生效口径：入口固定时优先生效，否则用推断（含强制切换）结果
const effectiveUsageType = computed(() => pinnedType ?? inferredType.value)

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
  pendingRows.value.push({ _key: Math.random().toString(36).slice(2), ...row })
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

// ─── 左侧工序侧栏（设计稿：工序列表 + 当日记录计数，点击筛选进度区） ──
const selectedTaskId = ref<number | null>(null)

/** 每个工序当日已有记录数（含待提交行），用于侧栏计数徽标 */
const taskDayCounts = computed<Record<number, number>>(() => {
  const counts: Record<number, number> = {}
  for (const r of existingRecords.value) {
    counts[r.taskId] = (counts[r.taskId] ?? 0) + 1
  }
  for (const r of pendingRows.value) {
    counts[r.task_id] = (counts[r.task_id] ?? 0) + 1
  }
  for (const u of reportStore.resourceUsages) {
    counts[u.taskId] = (counts[u.taskId] ?? 0) + 1
  }
  return counts
})

const totalDayCount = computed(() => Object.values(taskDayCounts.value).reduce((s, n) => s + n, 0))

// 侧栏选中工序时，进度区仅显示该工序（不影响提交数据）
const filteredInvolvedTaskIds = computed<number[]>(() => {
  const ids = involvedTaskIds.value
  return selectedTaskId.value === null ? ids : ids.filter((id) => id === selectedTaskId.value)
})

// ─── 碳排放计算结果（设计稿底部 3 统计卡，复用碳排聚合接口） ──────
import { useQuery } from '@pinia/colada'
import { getResourceUsageCarbonStatsQuery } from '@/client/@pinia/colada.gen'
import { useProjectApi } from '@/composables/useProjectApi'
import StatCard from '@/components/common/StatCard.vue'

const { project } = useProjectApi()

function useEmissionTotal(usageType: 'PLANNED' | 'ACTUAL') {
  const q = useQuery(() => ({
    ...getResourceUsageCarbonStatsQuery({
      path: { project_id: currentProjectId.value! },
      query: { usageType, granularity: 'month' },
    }),
    enabled: currentProjectId.value !== null,
  }))
  return computed(() => {
    const items = q.state.value?.data?.items ?? []
    return items.reduce((sum, it) => sum + (it.emission ?? 0), 0) / 1000
  })
}
const plannedEmissionT = useEmissionTotal('PLANNED')
const actualEmissionT = useEmissionTotal('ACTUAL')
const emissionLimitT = computed(() => project.value?.construction_carbon_emission_limit ?? null)

/** 统计卡数值格式化（千分位 + 1 位小数） */
function fmtNum(v: number): string {
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}

// ─── 统一提交：完成一天的录入 ──────────────────────────────
const { notifySuccess, notifyError } = useToast()

async function handleCompleteDay() {
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
        name: `手动录入 - ${usageDate.value}`,
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
  <!-- 设计稿布局：左侧工序侧栏 + 右侧录入区 -->
  <div class="grid grid-cols-1 lg:grid-cols-[230px_1fr] gap-4 items-start">
    <!-- 左：施工工序（process-item 列表 + 当日计数） -->
    <aside class="panel p-0 lg:sticky lg:top-4">
      <div class="px-4 py-3 border-b border-base-content/10">
        <h3 class="section-title m-0">施工工序</h3>
      </div>
      <div class="p-2 flex flex-col gap-0.5">
        <button
          type="button"
          class="process-item"
          :class="{ active: selectedTaskId === null }"
          @click="selectedTaskId = null"
        >
          <span>项目（全部）</span>
          <span class="pc">{{ totalDayCount }}</span>
        </button>
        <button
          v-for="t in scheduleTasks"
          :key="t.id"
          type="button"
          class="process-item sub"
          :class="{ active: selectedTaskId === t.id }"
          @click="selectedTaskId = selectedTaskId === t.id ? null : t.id"
        >
          <span class="truncate">{{ t.name }}</span>
          <span class="pc">{{ taskDayCounts[t.id] ?? 0 }}</span>
        </button>
        <p v-if="scheduleTasks.length === 0" class="text-xs text-fg-subtle px-3 py-2">
          暂无工序，请先到「施工工序管理」添加
        </p>
      </div>
    </aside>

    <!-- 右：录入内容 -->
    <div class="min-w-0">
  <!-- 顶部工具栏：日期 + 口径 + 从日报导入 -->
  <div class="panel mb-4">
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
      <span class="text-sm text-base-content/80">
        <template v-if="pinnedType">
          本入口固定按「{{ pinnedType === 'ACTUAL' ? '实际' : '计划' }}」口径录入
        </template>
        <template v-else>{{ inferenceReason }}</template>
      </span>
      <label v-if="!pinnedType" class="flex items-center gap-1 text-sm text-base-content/70 cursor-pointer">
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
    <div v-if="filteredInvolvedTaskIds.length === 0" class="text-sm text-fg-muted py-2">
      {{
        selectedTaskId !== null
          ? '该工序今日暂无涉及记录'
          : '暂无涉及工序（先补充手动用量或导入日报）'
      }}
    </div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-2">
      <div
        v-for="tid in filteredInvolvedTaskIds"
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

  <!-- 碳排放计算结果（设计稿底部统计卡） -->
  <div class="panel p-4 mt-4">
    <h3 class="section-title">碳排放计算结果</h3>
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <StatCard
        label="碳排放指标"
        :value="emissionLimitT === null ? '—' : fmtNum(emissionLimitT)"
        unit="tCO₂e"
        icon="target"
        color="primary"
      />
      <StatCard
        label="计划碳排"
        :value="fmtNum(plannedEmissionT)"
        unit="tCO₂e"
        icon="edit_calendar"
        color="warning"
      />
      <StatCard
        label="进度碳排"
        :value="fmtNum(actualEmissionT)"
        unit="tCO₂e"
        icon="trending_up"
        color="success"
      />
    </div>
  </div>

  <div v-if="submitErrorMessage" class="alert alert-error alert-sm mt-4" role="alert">
    <span class="material-symbols-outlined icon-sm">error</span>
    <span class="text-sm">{{ submitErrorMessage }}</span>
  </div>

  <div class="pt-4">
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
  </div>
</template>

<style scoped>
/* 工序侧栏条目（设计稿 process-item） */
.process-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 9px 12px;
  border-radius: 7px;
  font-size: 13px;
  color: var(--color-fg-muted);
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.12s,
    color 0.12s;
}
.process-item:hover {
  background: var(--color-base-200);
  color: var(--color-base-content);
}
.process-item.active {
  background: color-mix(in oklch, var(--color-primary) 10%, transparent);
  color: var(--color-primary);
  font-weight: 600;
}
.process-item.sub {
  padding-left: 24px;
}
.process-item .pc {
  font-size: 11.5px;
  color: var(--color-fg-subtle);
  background: var(--color-base-200);
  border-radius: 10px;
  padding: 0 8px;
  line-height: 18px;
  flex-shrink: 0;
}
.process-item.active .pc {
  background: var(--color-primary);
  color: var(--color-primary-content);
}
</style>
