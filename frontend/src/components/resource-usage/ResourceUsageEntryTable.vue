<script setup lang="ts">
/**
 * ResourceUsageEntryTable - 录入 tab 的待提交行表
 *
 * - 顶部：日期选择器（整个 batch 共享）、「单条录入」按钮、「从日报导入」按钮、「清空」按钮、行数统计
 * - 中部：表格行展示（只读）+ 行内编辑/删除按钮
 * - 编辑通过 ResourceUsageEntryForm 模态框完成
 * - 底部：「提交 N 条」按钮 + 错误列表
 */
import { computed, ref, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { useConfirm } from '@/composables/useConfirm'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import type { ResourceUsageBatchItem, ResourceUsageUpdate, UsageType } from '@/client/types.gen'
import type { ResourceCategory } from '@/types/resource'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import ResourceUsageEntryForm from './ResourceUsageEntryForm.vue'

/** 待提交行（包含前端临时 id） */
export interface PendingUsageRow {
  /** 前端临时 id，用于 key 和编辑 */
  _key: string
  task_id: number
  resource_id: number
  quantity: number
  /** 错误信息（行内） */
  error?: string
}

const {
  usageDate,
  usageType,
  batchLabel,
  existingCount,
  rows,
  submitErrorMessage,
  existingDuplicateKeys,
} = defineProps<{
  /** 当前 batch 的使用日期 */
  usageDate: string
  /** 当前 batch 的用量类型（实际 / 计划） */
  usageType: UsageType
  /** 本批次备注（原「批次名称」） */
  batchLabel: string
  /** 当日已有记录数 */
  existingCount?: number
  /** 待提交行 */
  rows: PendingUsageRow[]
  /** 提交错误信息（来自父组件的提交结果） */
  submitErrorMessage?: string
  /** 与已存在记录（其它 batch）冲突的行的 _key 集合 */
  existingDuplicateKeys?: Set<string>
}>()

const emit = defineEmits<{
  'update:usageType': [value: UsageType]
  'update:batchLabel': [value: string]
  'add-row': [row: Omit<PendingUsageRow, '_key' | 'error'>]
  'update-row': [key: string, row: Omit<PendingUsageRow, '_key' | 'error'>]
  'remove-row': [key: string]
  'clear-rows': []
  submit: [
    payload: {
      rows: Omit<PendingUsageRow, '_key' | 'error'>[]
      usageDate: string
    },
  ]
  'update:usageDate': [value: string]
}>()

const { confirmDanger } = useConfirm()
const { tasks } = useScheduleApi()
const router = useRouter()

// 编辑模态框状态
const showEditModal = ref(false)
const editingRow = ref<PendingUsageRow | null>(null)

// 资源下拉（使用「全部资源」时不分 category）
// 这里通过 useResourceApi 拉取第一个分类的初始值，然后切换时重新拉
// 简化处理：在 ResourceUsageEntryForm 内部处理

// 任务 / 资源 Map（用于显示行内数据）
const taskMap = computed(() => {
  const m = new Map<number, { code: string; name: string }>()
  for (const t of tasks.value) m.set(t.id, { code: t.code ?? '', name: t.name })
  return m
})

// 行内重复检测：(task_id, resource_id, usageDate) 唯一
const duplicateKeys = computed<Set<string>>(() => {
  const set = new Set<string>()
  const seen = new Map<string, string>() // key -> rowKey
  for (const r of rows) {
    const sig = `${r.task_id}|${r.resource_id}|${usageDate}`
    if (seen.has(sig)) {
      set.add(seen.get(sig)!)
      set.add(r._key)
    } else {
      seen.set(sig, r._key)
    }
  }
  return set
})

function getTaskDisplay(taskId: number) {
  const t = taskMap.value.get(taskId)
  if (!t) return `任务 #${taskId}`
  return t.code ? `${t.code} - ${t.name}` : t.name
}

// 资源名（仅展示），单位从 ResourceUsageEntryForm 拉取——为简化此处只展示 name
// 实际单位需要从 useResourceApi 取——下个组件会提供
const resourceNameMap = ref<
  Map<number, { name: string; unit: string; category: ResourceCategory }>
>(new Map())

const { currentProjectId } = useProjectContext()
const { state: resourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: FETCH_ALL_PAGE_SIZE },
  }),
)

// 跳转施工日报导入
function gotoDailyReportImport() {
  const id = currentProjectId.value
  if (id == null) return
  router.push(`/project/${id}/daily-report/import`)
}
watchEffect(() => {
  const list = resourcesState.value?.data?.items ?? []
  const m = new Map<number, { name: string; unit: string; category: ResourceCategory }>()
  for (const r of list) {
    m.set(r.id, { name: r.name, unit: r.unit, category: r.category })
  }
  resourceNameMap.value = m
})

function getResourceDisplay(resourceId: number) {
  const r = resourceNameMap.value.get(resourceId)
  if (!r) return `资源 #${resourceId}`
  return `${r.name} (${r.unit})`
}

function setMode(target: UsageType) {
  if (target !== usageType) emit('update:usageType', target)
}

const usageTypeOptions: ReadonlyArray<SegmentOption<UsageType>> = [
  { value: 'ACTUAL', label: '实际' },
  { value: 'PLANNED', label: '计划' },
]

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
  const r = await confirmDanger(`确定要清空全部 ${rows.length} 条待提交数据吗？`)
  if (r.confirmed) emit('clear-rows')
}

function handleSubmitAll() {
  const cleaned = rows
    .filter((r) => !duplicateKeys.value.has(r._key) && !crossBatchDuplicateKeys.value.has(r._key))
    .map((r) => ({
      task_id: r.task_id,
      resource_id: r.resource_id,
      quantity: r.quantity,
    }))
  emit('submit', {
    rows: cleaned,
    usageDate,
  })
}

/** 与已存在记录（同日其它批次）冲突的行 _key 集合 */
const crossBatchDuplicateKeys = computed<Set<string>>(
  () => existingDuplicateKeys ?? new Set<string>(),
)
/** 是否还有任何跨批次重复（用于禁用提交按钮） */
const hasCrossBatchDuplicates = computed(
  () =>
    crossBatchDuplicateKeys.value.size > 0 &&
    rows.some((r) => crossBatchDuplicateKeys.value.has(r._key)),
)

const tableHeaders = [
  { key: 'idx', label: '#', width: 'w-12' },
  { key: 'task', label: '工序', width: 'flex-1' },
  { key: 'resource', label: '资源', width: 'flex-1' },
  { key: 'quantity', label: '使用量', width: 'w-32', num: true },
  { key: 'actions', label: '操作', width: 'w-32' },
]
</script>

<template>
  <div class="space-y-4">
    <!-- 顶部工具栏 -->
    <div class="p-4 panel">
      <div class="px-5 py-4 border-b border-base-content/10 flex flex-wrap items-center gap-4">
        <div class="flex items-center gap-2">
          <label class="text-sm text-base-content/70">本批次使用日期：</label>
          <input
            type="date"
            :value="usageDate"
            class="input h-9 text-sm"
            @change="(e) => emit('update:usageDate', (e.target as HTMLInputElement).value)"
          />
        </div>
        <div class="flex items-center gap-2 flex-1 min-w-0">
          <label class="text-sm text-base-content/70 whitespace-nowrap">备注：</label>
          <input
            :value="batchLabel"
            type="text"
            class="input h-9 text-sm flex-1 min-w-0"
            placeholder="选填，例如：上午开挖批次"
            maxlength="100"
            @input="(e) => emit('update:batchLabel', (e.target as HTMLInputElement).value)"
          />
        </div>
        <div class="flex items-center gap-2 ml-auto">
          <span v-if="existingCount !== undefined" class="badge badge-sm badge-neutral">
            当日已有 {{ existingCount }} 条
          </span>
          <span class="badge badge-sm">已添加 {{ rows.length }} 条</span>
          <span v-if="duplicateKeys.size > 0" class="badge badge-sm badge-error">
            重复 {{ duplicateKeys.size }} 条
          </span>
          <span v-if="crossBatchDuplicateKeys.size > 0" class="badge badge-sm badge-warning">
            与已有记录冲突 {{ crossBatchDuplicateKeys.size }} 条
          </span>
        </div>
      </div>

      <div class="px-5 py-3 border-b border-base-content/10 flex flex-wrap items-center gap-3">
        <SegmentControl
          :model-value="usageType"
          :options="usageTypeOptions"
          aria-label="用量类型"
          @update:model-value="setMode"
        />
        <div class="flex items-center gap-2 ml-auto">
          <button class="btn btn-ghost btn-sm" :disabled="rows.length === 0" @click="handleClear">
            <span class="material-symbols-outlined icon-sm">delete_sweep</span>
            清空
          </button>
          <button class="btn btn-primary btn-sm gap-1" @click="handleAdd">
            <span class="material-symbols-outlined icon-sm">add</span>
            单条录入
          </button>
          <button type="button" class="btn btn-ghost btn-sm gap-1" @click="gotoDailyReportImport">
            <span class="material-symbols-outlined icon-sm">upload_file</span>
            从日报导入
          </button>
        </div>
      </div>

      <!-- 表格 -->
      <div class="p-4 space-y-4">
        <div v-if="rows.length === 0">
          <table>
            <TableEmptyState
              :colspan="tableHeaders.length"
              title="本批次暂无数据"
              description="点击「单条录入」添加第一条使用量记录"
              icon="edit_note"
            />
          </table>
        </div>
        <template v-else>
          <div class="panel p-0 overflow-x-auto">
            <table class="table">
              <thead>
                <tr>
                  <th
                    v-for="h in tableHeaders"
                    :key="h.key"
                    :class="[h.width, h.num ? 'table-num' : '']"
                  >
                    {{ h.label }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, idx) in rows"
                  :key="row._key"
                  class="hover:bg-base-content/5 transition-colors"
                  :class="{
                    'bg-error/10': duplicateKeys.has(row._key) || row.error,
                    'bg-warning/10':
                      !duplicateKeys.has(row._key) &&
                      !row.error &&
                      crossBatchDuplicateKeys.has(row._key),
                  }"
                >
                  <td>{{ idx + 1 }}</td>
                  <td>{{ getTaskDisplay(row.task_id) }}</td>
                  <td>{{ getResourceDisplay(row.resource_id) }}</td>
                  <td class="table-num">
                    <span class="font-num">{{ row.quantity }}</span>
                  </td>
                  <td>
                    <div class="flex items-center gap-1">
                      <button
                        class="btn btn-ghost btn-sm btn-square"
                        title="编辑"
                        @click="handleEdit(row)"
                      >
                        <span class="material-symbols-outlined icon-sm">edit</span>
                      </button>
                      <button
                        class="btn btn-ghost btn-sm btn-square text-error hover:bg-error/10"
                        title="移除"
                        @click="handleRemove(row)"
                      >
                        <span class="material-symbols-outlined icon-sm">delete</span>
                      </button>
                    </div>
                    <div v-if="duplicateKeys.has(row._key)" class="text-xs text-error mt-1">
                      与本批次内另一条记录重复
                    </div>
                    <div v-else-if="row.error" class="text-xs text-error mt-1">
                      {{ row.error }}
                    </div>
                    <div
                      v-else-if="crossBatchDuplicateKeys.has(row._key)"
                      class="text-xs text-warning mt-1"
                    >
                      此记录已存在于当日其它批次
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="submitErrorMessage" class="alert alert-error alert-sm">
            <span class="material-symbols-outlined icon-sm">error</span>
            <span class="text-sm">{{ submitErrorMessage }}</span>
          </div>

          <div class="flex justify-end">
            <button
              class="btn btn-primary"
              :disabled="rows.length === 0 || hasCrossBatchDuplicates"
              @click="handleSubmitAll"
            >
              <span class="material-symbols-outlined icon-sm">rocket_launch</span>
              提交 {{ rows.length }} 条
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- 编辑/单条录入模态框 -->
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
