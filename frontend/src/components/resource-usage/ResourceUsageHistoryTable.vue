<script setup lang="ts">
/**
 * ResourceUsageHistoryTable - 单个 batch 的记录表
 *
 * 列：任务、资源、数量、创建时间、操作
 * 行内：编辑（打开模态框）、删除（确认弹窗）
 */
import { computed, ref } from 'vue'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useConfirm } from '@/composables/useConfirm'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { watchEffect } from 'vue'
import type { ResourceCategory } from '@/types/resource'
import type { ResourceUsageResp, ResourceUsageUpdate } from '@/client/types.gen'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import ResourceUsageEntryForm from './ResourceUsageEntryForm.vue'

const { records, loading = false } = defineProps<{
  records: ResourceUsageResp[]
  loading?: boolean
}>()

const emit = defineEmits<{
  /** 删除单条 */
  delete: [id: number]
  /** 更新单条 */
  update: [id: number, data: ResourceUsageUpdate]
  /** 为用量打标 */
  tags: [usage: ResourceUsageResp]
}>()

const { confirmDanger } = useConfirm()
const { tasks } = useScheduleApi()
const { currentProjectId } = useProjectContext()

// 资源 Map
const { state: resourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: FETCH_ALL_PAGE_SIZE },
  }),
)
const resourceMap = ref<Map<number, { name: string; unit: string; category: ResourceCategory }>>(
  new Map(),
)
watchEffect(() => {
  const list = resourcesState.value?.data?.items ?? []
  const m = new Map<number, { name: string; unit: string; category: ResourceCategory }>()
  for (const r of list) m.set(r.id, { name: r.name, unit: r.unit, category: r.category })
  resourceMap.value = m
})

// 任务 Map
const taskMap = computed(() => {
  const m = new Map<number, { code: string; name: string }>()
  for (const t of tasks.value) m.set(t.id, { code: t.code ?? '', name: t.name })
  return m
})

function getTaskDisplay(id: number) {
  const t = taskMap.value.get(id)
  if (!t) return `任务 #${id}`
  return t.code ? `${t.code} - ${t.name}` : t.name
}
function getResourceDisplay(id: number) {
  const r = resourceMap.value.get(id)
  if (!r) return `资源 #${id}`
  return `${r.name} (${r.unit})`
}

const editingRecord = ref<ResourceUsageResp | null>(null)
const showEditModal = ref(false)

function handleEdit(rec: ResourceUsageResp) {
  editingRecord.value = rec
  showEditModal.value = true
}

function handleSubmitEdit(data: ResourceUsageUpdate) {
  if (editingRecord.value) {
    emit('update', editingRecord.value.id, data)
  }
  showEditModal.value = false
  editingRecord.value = null
}

async function handleDelete(rec: ResourceUsageResp) {
  const r = await confirmDanger(`确定要删除该使用量记录吗？此操作不可恢复。`)
  if (r.confirmed) emit('delete', rec.id)
}

const tableHeaders = [
  { key: 'task', label: '工序', width: 'flex-1' },
  { key: 'resource', label: '资源', width: 'flex-1' },
  { key: 'quantity', label: '使用量', width: 'w-32', num: true },
  { key: 'created', label: '创建时间', width: 'w-40' },
  { key: 'actions', label: '操作', width: 'w-32' },
]

function formatTime(iso: string) {
  return iso.slice(0, 19).replace('T', ' ')
}
</script>

<template>
  <div class="panel p-0">
    <div class="overflow-x-auto">
      <table class="table">
        <thead>
          <tr>
            <th v-for="h in tableHeaders" :key="h.key" :class="[h.width, h.num ? 'table-num' : '']">
              {{ h.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="records.length > 0">
            <tr
              v-for="rec in records"
              :key="rec.id"
              class="hover:bg-base-content/5 transition-colors"
            >
              <td>{{ getTaskDisplay(rec.taskId) }}</td>
              <td>{{ getResourceDisplay(rec.resourceId) }}</td>
              <td class="table-num">
                <span class="font-num">{{ rec.quantity }}</span>
              </td>
              <td class="text-sm text-base-content/70">{{ formatTime(rec.createdAt) }}</td>
              <td>
                <div class="flex items-center gap-1">
                  <button
                    class="btn btn-ghost btn-sm btn-square"
                    title="为用量打标"
                    @click="emit('tags', rec)"
                  >
                    <span class="material-symbols-outlined icon-sm">label</span>
                  </button>
                  <button
                    class="btn btn-ghost btn-sm btn-square"
                    title="编辑"
                    @click="handleEdit(rec)"
                  >
                    <span class="material-symbols-outlined icon-sm">edit</span>
                  </button>
                  <button
                    class="btn btn-ghost btn-sm btn-square text-error hover:bg-error/10"
                    title="删除"
                    @click="handleDelete(rec)"
                  >
                    <span class="material-symbols-outlined icon-sm">delete</span>
                  </button>
                </div>
              </td>
            </tr>
          </template>
          <TableEmptyState
            v-else
            :colspan="tableHeaders.length"
            title="该批次暂无记录"
            icon="inbox"
          />
        </tbody>
      </table>
    </div>

    <ResourceUsageEntryForm
      v-model:show="showEditModal"
      mode="update"
      :initial-value="
        editingRecord
          ? {
              task_id: editingRecord.taskId,
              resource_id: editingRecord.resourceId,
              quantity: editingRecord.quantity,
            }
          : null
      "
      title="编辑使用量"
      @submit="handleSubmitEdit"
      @cancel="editingRecord = null"
    />
  </div>
</template>
