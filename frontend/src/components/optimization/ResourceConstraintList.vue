<script setup lang="ts">
import { computed } from 'vue'
import type { ResourceConstraintResp } from '@/types/constraint'
import { useConfirm } from '@/composables/useConfirm'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'

defineProps<{
  constraints: ResourceConstraintResp[]
}>()

const emit = defineEmits<{
  (e: 'edit', constraint: ResourceConstraintResp): void
  (e: 'delete', constraint: ResourceConstraintResp): void
}>()

const { confirmDanger } = useConfirm()

// 获取资源列表用于查找名称
const { currentProjectId } = useProjectContext()
const { state: resourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: {},
  }),
)
const resourceMap = computed(() => {
  const map = new Map<number, string>()
  const resources = resourcesState.value?.data?.items ?? []
  resources.forEach((r) => {
    map.set(r.id, r.name)
  })
  return map
})

const getResourceName = (resourceId: number) => {
  return resourceMap.value.get(resourceId) ?? `资源 #${resourceId}`
}

const handleDelete = async (constraint: ResourceConstraintResp) => {
  const result = await confirmDanger(
    `确定要删除资源"${getResourceName(constraint.resourceId)}"的限制吗？`,
  )
  if (result.confirmed) {
    emit('delete', constraint)
  }
}
</script>

<template>
  <div v-if="constraints.length === 0" class="py-8">
    <div class="flex flex-col items-center gap-3 text-fg-muted">
      <span class="material-symbols-outlined icon-lg opacity-50">rule</span>
      <p class="text-sm">暂无资源限制</p>
    </div>
  </div>

  <div v-else class="overflow-x-auto">
    <table class="table">
      <thead>
        <tr>
          <th>资源名称</th>
          <th class="w-32 table-num">最大使用量</th>
          <th class="flex-1">备注</th>
          <th class="w-24 text-right">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="constraint in constraints" :key="constraint.id" class="hover:bg-base-content/5">
          <td>
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined icon-sm text-primary/70">rule</span>
              {{ getResourceName(constraint.resourceId) }}
            </div>
          </td>
          <td class="table-num">
            <span class="font-num">{{ constraint.maxUsage }}</span>
          </td>
          <td>
            <span v-if="constraint.description">{{ constraint.description }}</span>
            <span v-else class="text-fg-muted">-</span>
          </td>
          <td class="text-right">
            <div class="flex items-center justify-end gap-1">
              <button
                class="btn btn-xs btn-ghost gap-1 text-fg-muted hover:text-primary"
                @click="emit('edit', constraint)"
              >
                <span class="material-symbols-outlined text-base">edit</span>
                编辑
              </button>
              <button
                class="btn btn-xs btn-ghost gap-1 text-fg-muted hover:text-error"
                @click="handleDelete(constraint)"
              >
                <span class="material-symbols-outlined text-base">delete</span>
                删除
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
