<script setup lang="ts">
/**
 * UsageEntrySummary - 录入页统一「待提交数据」汇总卡片
 *
 * - 日报导入与手动录入并排展示，无独立「手动录入」区块
 * - 来源用徽标 border 区分：手动 = 虚线边框，日报 = 实线边框（参考 ParetoWeightsBar）
 * - 手动徽标内含 资源名 + 数量 + edit 小按钮 + close 圆钮（编辑与删除并排）
 * - 按工序 / 按资源 两种视角切换
 *
 * 日报 store（stores/report.ts）由本组件直接读取（batchId / allocatedResourceQuantities / reset）；
 * 手动待提交行由父组件（entry.vue）传入。
 */
import { computed, ref } from 'vue'
import { useQuery } from '@pinia/colada'
import { useConfirm } from '@/composables/useConfirm'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useDailyReportStoreV2 } from '@/stores/report'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import type { UsageType } from '@/client/types.gen'
import type { ResourceCategory } from '@/types/resource'
import ResourceUsageEntryForm from './ResourceUsageEntryForm.vue'

/** 待提交手动行（与旧 ManualUsageByTask 同构） */
export interface PendingUsageRow {
  _key: string
  task_id: number
  resource_id: number
  quantity: number
  error?: string
}

/** 统一展示条目：来自日报或手动 */
interface DisplayEntry {
  /** 来源 */
  source: 'daily' | 'manual'
  /** 资源名 */
  resourceName: string
  /** 资源单位（手动条目经 listResourcesQuery 映射；日报条目无单位） */
  unit?: string
  quantity: number
  /** 手动行 key（手动条目专属） */
  rowKey?: string
  /** 冲突标记（手动条目与当日已有同口径记录冲突） */
  conflict?: boolean
}

const { manualRows, usageDate, usageType, existingDuplicateKeys } = defineProps<{
  /** 手动待提交行 */
  manualRows: PendingUsageRow[]
  /** 当前使用日期（仅用于编辑弹窗默认值） */
  usageDate: string
  /** 当前用量类型（仅用于编辑弹窗标签） */
  usageType: UsageType
  /** 与已存在记录（同日同口径其它批次）冲突的手动行 _key 集合 */
  existingDuplicateKeys?: Set<string>
}>()

const emit = defineEmits<{
  'add-row': [row: Omit<PendingUsageRow, '_key' | 'error'>]
  'update-row': [key: string, row: Omit<PendingUsageRow, '_key' | 'error'>]
  'remove-row': [key: string]
  'remove-batch': []
}>()

const { confirmDanger } = useConfirm()
const store = useDailyReportStoreV2()
const { currentProjectId } = useProjectContext()

// 任务名 / 资源名映射
const { tasks } = useScheduleApi()
const taskMap = computed(() => {
  const m = new Map<number, { code: string; name: string }>()
  for (const t of tasks.value) m.set(t.id, { code: t.code ?? '', name: t.name })
  return m
})
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

// ─── 数据源归一化 ──────────────────────────────────────────

/** 日报条目：按任务聚合（Map<taskId, Array<{resourceName, quantity}>>） */
const dailyByTask = computed(() => {
  const m = new Map<number, DisplayEntry[]>()
  for (const [taskId, resourceQuantities] of store.allocatedResourceQuantities.entries()) {
    const list: DisplayEntry[] = []
    for (const [resourceName, quantity] of Object.entries(resourceQuantities)) {
      if (quantity !== 0) list.push({ source: 'daily', resourceName, quantity })
    }
    if (list.length > 0) m.set(taskId, list)
  }
  return m
})

/** 日报条目：按资源名聚合（Map<resourceName, Array<{taskId, quantity}>>） */
const dailyByResource = computed(() => {
  const m = new Map<string, { taskId: number; quantity: number }[]>()
  for (const u of store.resourceUsages) {
    const list = m.get(u.resourceName) ?? []
    list.push({ taskId: u.taskId, quantity: u.quantity })
    m.set(u.resourceName, list)
  }
  return m
})

/** 手动条目（带资源名映射），按任务聚合 */
const manualByTask = computed(() => {
  const m = new Map<number, DisplayEntry[]>()
  for (const r of manualRows) {
    const res = resourceMap.value.get(r.resource_id)
    const conflict = existingDuplicateKeys?.has(`${r.task_id}|${r.resource_id}`) ?? false
    const list = m.get(r.task_id) ?? []
    list.push({
      source: 'manual',
      resourceName: res?.name ?? `资源 #${r.resource_id}`,
      unit: res?.unit,
      quantity: r.quantity,
      rowKey: r._key,
      conflict,
    })
    m.set(r.task_id, list)
  }
  return m
})

/** 手动条目按资源名聚合（Map<resourceName, Array<DisplayEntry>>） */
const manualByResource = computed(() => {
  const m = new Map<string, DisplayEntry[]>()
  for (const r of manualRows) {
    const res = resourceMap.value.get(r.resource_id)
    const name = res?.name ?? `资源 #${r.resource_id}`
    const conflict = existingDuplicateKeys?.has(`${r.task_id}|${r.resource_id}`) ?? false
    const list = m.get(name) ?? []
    list.push({
      source: 'manual',
      resourceName: name,
      unit: res?.unit,
      quantity: r.quantity,
      rowKey: r._key,
      conflict,
    })
    m.set(name, list)
  }
  return m
})

// ─── 视图切换 ──────────────────────────────────────────────

type ViewMode = 'task' | 'resource'
const activeView = ref<ViewMode>('task')

/** 按工序视图：日报 ∪ 手动 的任务并集 */
const taskEntries = computed<Array<{ taskId: number; entries: DisplayEntry[] }>>(() => {
  const ids = new Set<number>([...dailyByTask.value.keys(), ...manualByTask.value.keys()])
  return Array.from(ids)
    .sort((a, b) =>
      (taskMap.value.get(a)?.code ?? '').localeCompare(taskMap.value.get(b)?.code ?? ''),
    )
    .map((taskId) => ({
      taskId,
      entries: [
        ...(dailyByTask.value.get(taskId) ?? []),
        ...(manualByTask.value.get(taskId) ?? []),
      ],
    }))
})

/** 按资源视图：日报 ∪ 手动 的资源名并集 */
const resourceEntries = computed<Array<{ resourceName: string; entries: DisplayEntry[] }>>(() => {
  const names = new Set<string>([...dailyByResource.value.keys(), ...manualByResource.value.keys()])
  return Array.from(names)
    .sort((a, b) => a.localeCompare(b, 'zh-CN'))
    .map((resourceName) => {
      const daily = (dailyByResource.value.get(resourceName) ?? []).map<DisplayEntry>((d) => ({
        source: 'daily',
        resourceName,
        quantity: d.quantity,
      }))
      const manual = manualByResource.value.get(resourceName) ?? []
      return { resourceName, entries: [...daily, ...manual] }
    })
})

// ─── 统计 ──────────────────────────────────────────────────

/** 解析资源项数（日报原始解析项） */
const parsedCount = computed(() => store.parsedResourceItems.length)
/** 日报分配工序数 / 分配项数 */
const dailyTaskCount = computed(() => dailyByTask.value.size)
const dailyItemCount = computed(() => store.resourceUsages.length)
/** 手动条数 */
const manualCount = computed(() => manualRows.length)

const hasPendingBatch = computed(() => !!store.batchId && store.resourceUsages.length > 0)
const shortBatchId = computed(() => (store.batchId ? store.batchId.slice(0, 8) : ''))

// ─── 编辑弹窗 ──────────────────────────────────────────────

const showEditModal = ref(false)
const editingRow = ref<PendingUsageRow | null>(null)

function handleAdd() {
  editingRow.value = null
  showEditModal.value = true
}

function handleEdit(row: PendingUsageRow) {
  editingRow.value = row
  showEditModal.value = true
}

function handleSubmitEdit(data: { task_id?: number; resource_id?: number; quantity?: number }) {
  const taskId = data.task_id ?? editingRow.value?.task_id
  const resourceId = data.resource_id ?? editingRow.value?.resource_id
  const quantity = data.quantity ?? editingRow.value?.quantity
  if (taskId == null || resourceId == null || quantity == null) return
  if (editingRow.value) {
    emit('update-row', editingRow.value._key, {
      task_id: taskId,
      resource_id: resourceId,
      quantity,
    })
  } else {
    emit('add-row', { task_id: taskId, resource_id: resourceId, quantity })
  }
  showEditModal.value = false
  editingRow.value = null
}

async function handleRemoveRow(row: PendingUsageRow) {
  const r = await confirmDanger(`确定要移除这条待提交的手动使用量吗？`)
  if (r.confirmed) emit('remove-row', row._key)
}

async function handleRemoveBatch() {
  const r = await confirmDanger(
    '确定要移除这个待提交的日报批次吗？已解析的资源映射与分配数据将一并清除，需重新导入。',
  )
  if (r.confirmed) emit('remove-batch')
}

// ─── 徽标渲染辅助 ──────────────────────────────────────────

function taskDisplay(taskId: number) {
  const t = taskMap.value.get(taskId)
  if (!t) return `工序 #${taskId}`
  return `${t.code} - ${t.name}`
}

function taskCode(taskId: number) {
  return taskMap.value.get(taskId)?.code ?? `#${taskId}`
}
</script>

<template>
  <div class="panel p-0">
    <!-- 标题行 -->
    <div class="px-5 py-3 border-b border-base-content/10 flex flex-wrap items-center gap-3">
      <h3 class="text-sm font-semibold text-base-content flex items-center gap-2">
        <span class="material-symbols-outlined icon-sm text-fg-muted">inventory_2</span>
        待提交数据
        <span class="badge badge-sm badge-neutral">日报导入</span>
        <span class="badge badge-sm badge-outline border-dashed">手动</span>
        <span v-if="hasPendingBatch" class="text-xs text-fg-subtle font-mono"
          >#{{ shortBatchId }}</span
        >
      </h3>
      <div class="flex items-center gap-2 ml-auto">
        <span class="badge badge-sm">解析 {{ parsedCount }} 项</span>
        <span class="badge badge-sm">工序 {{ dailyTaskCount }}</span>
        <span class="badge badge-sm">分配 {{ dailyItemCount }} 项</span>
        <span class="badge badge-sm">手动 {{ manualCount }} 条</span>
        <button
          v-if="hasPendingBatch"
          class="btn btn-ghost btn-sm text-error"
          @click="handleRemoveBatch"
        >
          <span class="material-symbols-outlined icon-sm">delete_sweep</span>
          移除批次
        </button>
      </div>
    </div>

    <div class="p-4 space-y-3">
      <!-- 空态 -->
      <div v-if="taskEntries.length === 0" class="text-center py-8 text-sm text-fg-muted">
        暂无待提交数据，点击「+补充」手动录入，或从日报导入解析后分配。
      </div>

      <template v-else>
        <!-- 视图切换 -->
        <div class="join grid grid-cols-2 w-72">
          <button
            type="button"
            class="join-item btn btn-sm"
            :class="activeView === 'task' ? 'btn-primary' : 'btn-outline'"
            @click="activeView = 'task'"
          >
            <span class="material-symbols-outlined icon-sm">construction</span>
            按工序汇总
          </button>
          <button
            type="button"
            class="join-item btn btn-sm"
            :class="activeView === 'resource' ? 'btn-primary' : 'btn-outline'"
            @click="activeView = 'resource'"
          >
            <span class="material-symbols-outlined icon-sm">inventory_2</span>
            按资源汇总
          </button>
        </div>

        <!-- 按工序视图 -->
        <div v-if="activeView === 'task'" class="flex flex-col gap-2 mt-2">
          <div
            v-for="group in taskEntries"
            :key="group.taskId"
            class="rounded-lg border border-base-300 px-4 py-3"
          >
            <h4 class="font-medium text-base-content text-sm mb-2">
              {{ taskDisplay(group.taskId) }}
            </h4>
            <div class="flex flex-wrap items-center gap-2">
              <!-- 日报条目：实线徽标 -->
              <span
                v-for="(e, i) in group.entries.filter((x) => x.source === 'daily')"
                :key="`daily-${i}`"
                class="inline-flex items-center gap-1 h-7 px-3 rounded-full border text-[11px] bg-primary/15 border-primary/40 text-primary"
              >
                <span class="truncate">{{ e.resourceName }}</span>
                <span class="font-num">{{ e.quantity }}</span>
              </span>
              <!-- 手动条目：虚线徽标 + 编辑 + 删除 -->
              <span
                v-for="e in group.entries.filter((x) => x.source === 'manual')"
                :key="`manual-${e.rowKey}`"
                class="inline-flex items-center gap-1 h-7 pl-3 pr-1 rounded-full border border-dashed text-[11px] transition-colors"
                :class="
                  e.conflict
                    ? 'bg-warning/10 border-warning/50 text-warning'
                    : 'bg-primary/10 border-primary/30 text-primary hover:bg-primary/15'
                "
              >
                <span class="truncate" :title="`${e.resourceName}${e.unit ? ` (${e.unit})` : ''}`">
                  {{ e.resourceName }}
                </span>
                <span class="font-num">{{ e.quantity }}</span>
                <button
                  type="button"
                  class="w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-base-content/40 hover:text-primary hover:bg-primary/10"
                  :aria-label="`编辑 ${e.resourceName}`"
                  @click="handleEdit(manualRows.find((r) => r._key === e.rowKey)!)"
                >
                  <span class="material-symbols-outlined text-sm">edit</span>
                </button>
                <button
                  type="button"
                  class="w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-base-content/40 hover:text-error hover:bg-error/10"
                  :aria-label="`删除 ${e.resourceName}`"
                  @click="handleRemoveRow(manualRows.find((r) => r._key === e.rowKey)!)"
                >
                  <span class="material-symbols-outlined text-sm">close</span>
                </button>
              </span>
            </div>
          </div>
        </div>

        <!-- 按资源视图 -->
        <div v-else class="flex flex-col gap-2 mt-2">
          <div
            v-for="group in resourceEntries"
            :key="group.resourceName"
            class="rounded-lg border border-base-300 px-4 py-3"
          >
            <h4 class="font-medium text-base-content text-sm mb-2">{{ group.resourceName }}</h4>
            <div class="flex flex-wrap items-center gap-2">
              <!-- 日报条目（按资源视角）：实线徽标，显示工序 code + 数量 -->
              <span
                v-for="(e, i) in group.entries.filter((x) => x.source === 'daily')"
                :key="`daily-${i}`"
                class="inline-flex items-center gap-1 h-7 px-3 rounded-full border text-[11px] bg-primary/15 border-primary/40 text-primary"
              >
                <span class="italic">{{
                  taskCode((dailyByResource.get(group.resourceName) ?? [])[i]?.taskId ?? 0)
                }}</span>
                <span class="font-num">{{ e.quantity }}</span>
              </span>
              <!-- 手动条目：虚线徽标 + 编辑 + 删除 -->
              <span
                v-for="e in group.entries.filter((x) => x.source === 'manual')"
                :key="`manual-${e.rowKey}`"
                class="inline-flex items-center gap-1 h-7 pl-3 pr-1 rounded-full border border-dashed text-[11px] transition-colors"
                :class="
                  e.conflict
                    ? 'bg-warning/10 border-warning/50 text-warning'
                    : 'bg-primary/10 border-primary/30 text-primary hover:bg-primary/15'
                "
              >
                <span class="truncate" :title="`${e.resourceName}${e.unit ? ` (${e.unit})` : ''}`">
                  {{
                    taskCode(
                      e.rowKey ? (manualRows.find((r) => r._key === e.rowKey)?.task_id ?? 0) : 0,
                    )
                  }}
                </span>
                <span class="font-num">{{ e.quantity }}</span>
                <button
                  type="button"
                  class="w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-base-content/40 hover:text-primary hover:bg-primary/10"
                  :aria-label="`编辑 ${e.resourceName}`"
                  @click="handleEdit(manualRows.find((r) => r._key === e.rowKey)!)"
                >
                  <span class="material-symbols-outlined text-sm">edit</span>
                </button>
                <button
                  type="button"
                  class="w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-base-content/40 hover:text-error hover:bg-error/10"
                  :aria-label="`删除 ${e.resourceName}`"
                  @click="handleRemoveRow(manualRows.find((r) => r._key === e.rowKey)!)"
                >
                  <span class="material-symbols-outlined text-sm">close</span>
                </button>
              </span>
            </div>
          </div>
        </div>

        <!-- +补充 虚线胶囊 -->
        <div class="flex justify-end pt-1">
          <button
            type="button"
            class="inline-flex items-center gap-1 h-7 px-3 rounded-full border border-dashed text-[11px] transition-colors bg-base-200/40 border-base-content/20 text-fg-muted hover:border-primary/40 hover:text-base-content"
            @click="handleAdd"
          >
            <span class="material-symbols-outlined text-xs">add</span>
            +补充
          </button>
        </div>
      </template>
    </div>

    <!-- 补充/编辑弹窗 -->
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
      :title="editingRow ? '编辑使用量' : '补充使用量'"
      @submit="handleSubmitEdit"
      @cancel="editingRow = null"
    />
  </div>
</template>
