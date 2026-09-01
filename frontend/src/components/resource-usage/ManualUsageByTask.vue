<script setup lang="ts">
/**
 * ManualUsageByTask - 手动录入的「按工序汇总」可编辑卡片
 *
 * - 数据源为手动待提交行（PendingUsageRow[]，非日报 store），与日报解耦
 * - 按 task_id 分组，每工序卡片内列出 (resource, quantity)
 * - 来源粒度标记：每行小徽标「手动」；工序内全部资源均为手动录入时工序标题旁徽标「手动录入」
 * - 操作：添加资源（弹窗 EntryForm）、编辑、删除行、清空
 * - 重复检测：行内 (task, resource) 重复 + 跨批次（与已存在记录同口径）冲突
 */
import { computed, ref } from 'vue'
import { useConfirm } from '@/composables/useConfirm'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import type { ResourceUsageBatchItem, ResourceUsageUpdate, UsageType } from '@/client/types.gen'
import type { ResourceCategory } from '@/types/resource'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import ResourceUsageEntryForm from './ResourceUsageEntryForm.vue'

/** 待提交行（与 ResourceUsageEntryTable 同构，避免依赖日报 store） */
export interface PendingUsageRow {
  /** 前端临时 id，用于 key 和编辑 */
  _key: string
  task_id: number
  resource_id: number
  quantity: number
  /** 错误信息（行内） */
  error?: string
}

const { rows, usageDate, usageType, reportTaskIds, existingDuplicateKeys } = defineProps<{
  /** 待提交手动行 */
  rows: PendingUsageRow[]
  /** 当前使用日期（仅用于行内重复签名） */
  usageDate: string
  /** 当前用量类型（仅用于冲突语义展示） */
  usageType: UsageType
  /** 日报批次涉及的工序 id（用于判断「全手动工序」徽标） */
  reportTaskIds?: number[]
  /** 与已存在记录（同日同口径其它批次）冲突的行的 _key 集合 */
  existingDuplicateKeys?: Set<string>
}>()

const emit = defineEmits<{
  'add-row': [row: Omit<PendingUsageRow, '_key' | 'error'>]
  'update-row': [key: string, row: Omit<PendingUsageRow, '_key' | 'error'>]
  'remove-row': [key: string]
  'clear-rows': []
}>()

const { confirmDanger } = useConfirm()
const { tasks } = useScheduleApi()

// 编辑模态框状态
const showEditModal = ref(false)
const editingRow = ref<PendingUsageRow | null>(null)

// 资源 Map（用于显示名称/单位）
const { currentProjectId } = useProjectContext()
const { state: resourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: FETCH_ALL_PAGE_SIZE },
  }),
)
const resourceMap = computed<
  Map<number, { name: string; unit: string; category: ResourceCategory }>
>(() => {
  const m = new Map<number, { name: string; unit: string; category: ResourceCategory }>()
  for (const r of resourcesState.value?.data?.items ?? []) {
    m.set(r.id, { name: r.name, unit: r.unit, category: r.category })
  }
  return m
})

const taskMap = computed(() => {
  const m = new Map<number, { code: string; name: string }>()
  for (const t of tasks.value) m.set(t.id, { code: t.code ?? '', name: t.name })
  return m
})

/** 该工序是否「全部为手动录入」：有手动行且不在日报批次涉及工序中 */
function isFullyManual(taskId: number): boolean {
  const hasManualRows = rows.some((r) => r.task_id === taskId)
  if (!hasManualRows) return false
  if (reportTaskIds && reportTaskIds.includes(taskId)) return false
  return true
}

function getTaskDisplay(taskId: number) {
  const t = taskMap.value.get(taskId)
  if (!t) return `工序 #${taskId}`
  return t.code ? `${t.code} - ${t.name}` : t.name
}

function getResourceDisplay(resourceId: number) {
  const r = resourceMap.value.get(resourceId)
  if (!r) return `资源 #${resourceId}`
  return `${r.name} (${r.unit})`
}

/** 按工序分组（保持首次出现顺序） */
const grouped = computed<Map<number, PendingUsageRow[]>>(() => {
  const m = new Map<number, PendingUsageRow[]>()
  for (const r of rows) {
    const list = m.get(r.task_id) ?? []
    list.push(r)
    m.set(r.task_id, list)
  }
  return m
})

/** 行内重复：(task_id, resource_id) 在当前手动行中重复 */
const intraDuplicateKeys = computed<Set<string>>(() => {
  const set = new Set<string>()
  const seen = new Map<string, string>()
  for (const r of rows) {
    const sig = `${r.task_id}|${r.resource_id}`
    if (seen.has(sig)) {
      set.add(seen.get(sig)!)
      set.add(r._key)
    } else {
      seen.set(sig, r._key)
    }
  }
  return set
})

/** 与已存在记录（同日同口径其它批次）冲突的行 _key 集合 */
const crossBatchDuplicateKeys = computed<Set<string>>(
  () => existingDuplicateKeys ?? new Set<string>(),
)
const hasCrossBatchDuplicates = computed(
  () =>
    crossBatchDuplicateKeys.value.size > 0 &&
    rows.some((r) => crossBatchDuplicateKeys.value.has(r._key)),
)

function handleAdd() {
  editingRow.value = null
  showEditModal.value = true
}

function handleEdit(row: PendingUsageRow) {
  editingRow.value = row
  showEditModal.value = true
}

function handleSubmitEdit(data: ResourceUsageBatchItem | ResourceUsageUpdate) {
  if ('task_id' in data && data.task_id !== undefined) {
    const d = data as ResourceUsageBatchItem
    if (editingRow.value) {
      emit('update-row', editingRow.value._key, {
        task_id: d.task_id,
        resource_id: d.resource_id,
        quantity: d.quantity,
      })
    } else {
      emit('add-row', {
        task_id: d.task_id,
        resource_id: d.resource_id,
        quantity: d.quantity,
      })
    }
  } else if (editingRow.value) {
    const d = data as ResourceUsageUpdate
    emit('update-row', editingRow.value._key, {
      task_id: d.taskId ?? editingRow.value.task_id,
      resource_id: d.resourceId ?? editingRow.value.resource_id,
      quantity: d.quantity ?? editingRow.value.quantity,
    })
  }
  showEditModal.value = false
  editingRow.value = null
}

async function handleRemove(row: PendingUsageRow) {
  const r = await confirmDanger(`确定要移除这条待提交的使用量数据吗？`)
  if (r.confirmed) emit('remove-row', row._key)
}

async function handleClear() {
  if (rows.length === 0) return
  const r = await confirmDanger(`确定要清空全部 ${rows.length} 条手动待提交数据吗？`)
  if (r.confirmed) emit('clear-rows')
}
</script>

<template>
  <div class="panel p-0">
    <div class="px-5 py-3 border-b border-base-content/10 flex flex-wrap items-center gap-3">
      <h3 class="text-sm font-semibold text-base-content flex items-center gap-2">
        <span class="material-symbols-outlined icon-sm text-fg-muted">edit_note</span>
        手动录入
        <span class="badge badge-sm badge-info">手动</span>
      </h3>
      <div class="flex items-center gap-2 ml-auto">
        <span class="badge badge-sm">已添加 {{ rows.length }} 条</span>
        <span v-if="intraDuplicateKeys.size > 0" class="badge badge-sm badge-error">
          重复 {{ intraDuplicateKeys.size }} 条
        </span>
        <span v-if="hasCrossBatchDuplicates" class="badge badge-sm badge-warning">
          与已有记录冲突
        </span>
        <button class="btn btn-ghost btn-sm" :disabled="rows.length === 0" @click="handleClear">
          <span class="material-symbols-outlined icon-sm">delete_sweep</span>
          清空
        </button>
        <button class="btn btn-primary btn-sm gap-1" @click="handleAdd">
          <span class="material-symbols-outlined icon-sm">add</span>
          添加记录
        </button>
      </div>
    </div>

    <div class="p-4 space-y-3">
      <!-- 空态 -->
      <div v-if="rows.length === 0">
        <table class="table">
          <TableEmptyState
            :colspan="4"
            title="暂无手动录入数据"
            description="点击「添加记录」按工序录入使用量；或先通过「从日报导入」解析后在此汇总"
            icon="edit_note"
          />
        </table>
      </div>

      <!-- 按工序分组卡片 -->
      <div
        v-for="[taskId, taskRows] in grouped"
        :key="taskId"
        class="rounded-lg border border-base-300"
      >
        <div class="flex flex-row justify-between items-center px-4 py-3">
          <div class="flex flex-wrap items-center gap-3">
            <h4 class="font-medium text-base-content text-sm">
              {{ getTaskDisplay(taskId) }}
            </h4>
            <!-- 工序级来源标记：全部手动 -->
            <span v-if="isFullyManual(taskId)" class="badge badge-sm badge-info">手动录入</span>
            <span class="badge badge-sm badge-neutral">{{ taskRows.length }} 条</span>
          </div>
        </div>

        <div class="px-4 pb-3 space-y-2">
          <div
            v-for="row in taskRows"
            :key="row._key"
            class="flex items-center gap-2 rounded-lg border border-base-content/10 px-3 py-2"
            :class="{
              'bg-error/10': intraDuplicateKeys.has(row._key) || row.error,
              'bg-warning/10':
                !intraDuplicateKeys.has(row._key) &&
                !row.error &&
                crossBatchDuplicateKeys.has(row._key),
            }"
          >
            <span class="badge badge-xs badge-info shrink-0">手动</span>
            <span class="flex-1 min-w-0 truncate text-sm">
              {{ getResourceDisplay(row.resource_id) }}
            </span>
            <span class="font-num text-sm shrink-0">{{ row.quantity }}</span>
            <button
              class="btn btn-ghost btn-xs btn-square shrink-0"
              title="编辑"
              @click="handleEdit(row)"
            >
              <span class="material-symbols-outlined icon-xs">edit</span>
            </button>
            <button
              class="btn btn-ghost btn-xs btn-square text-error hover:bg-error/10 shrink-0"
              title="移除"
              @click="handleRemove(row)"
            >
              <span class="material-symbols-outlined icon-xs">delete</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加/编辑模态框 -->
    <ResourceUsageEntryForm
      v-model:show="showEditModal"
      :mode="editingRow ? 'update' : 'create'"
      :usage-date="usageDate"
      :usage-type="usageType"
      :initial-value="
        editingRow
          ? {
              task_id: editingRow.task_id,
              resource_id: editingRow.resource_id,
              quantity: editingRow.quantity,
            }
          : null
      "
      :title="editingRow ? '编辑使用量' : '添加使用量'"
      @submit="handleSubmitEdit"
      @cancel="editingRow = null"
    />
  </div>
</template>
