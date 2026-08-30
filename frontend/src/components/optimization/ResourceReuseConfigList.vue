<script setup lang="ts">
import { computed } from 'vue'
import type { ResourceReuseConfigResp } from '@/types/reuseConfig'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import { useConfirm } from '@/composables/useConfirm'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'

defineProps<{
  configs: ResourceReuseConfigResp[]
}>()

const emit = defineEmits<{
  (e: 'edit', config: ResourceReuseConfigResp): void
  (e: 'delete', config: ResourceReuseConfigResp): void
}>()

const { confirmDanger } = useConfirm()

// 获取材料资源列表用于查找名称
const { currentProjectId } = useProjectContext()
const { state: resourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { category: 'material' },
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
  return resourceMap.value.get(resourceId) ?? `材料 #${resourceId}`
}

const handleDelete = async (config: ResourceReuseConfigResp) => {
  const result = await confirmDanger(
    `确定要删除材料"${getResourceName(config.resourceId)}"的复用配置吗？`,
  )
  if (result.confirmed) {
    emit('delete', config)
  }
}

const tableHeaders = [
  { key: 'resourceName', label: '材料名称', width: 'flex-1' },
  { key: 'maxReuses', label: '最大周转次数', width: 'w-32', num: true },
  { key: 'reuseCount', label: '实际周转次数', width: 'w-32', num: true },
  { key: 'affectCost', label: '是否影响成本', width: 'w-32' },
  { key: 'description', label: '备注', width: 'flex-1' },
  { key: 'actions', label: '操作', width: 'w-24' },
]
</script>

<template>
  <div class="overflow-x-auto">
    <table class="table">
      <thead>
        <tr>
          <th
            v-for="header in tableHeaders"
            :key="header.key"
            :class="[header.width, header.num ? 'table-num' : '']"
          >
            {{ header.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-if="configs.length > 0">
          <tr
            v-for="config in configs"
            :key="config.id"
            class="hover:bg-base-300/30 transition-colors"
          >
            <td>
              <div class="font-medium text-base-content">
                {{ getResourceName(config.resourceId) }}
              </div>
            </td>
            <td class="table-num">
              <span class="font-num text-base-content">{{ config.maxReuses }}</span>
            </td>
            <td class="table-num">
              <span class="font-num text-base-content">{{ config.reuseCount }}</span>
            </td>
            <td>
              <span
                class="badge badge-sm"
                :class="{
                  'badge-primary': config.affectCost,
                  'badge-ghost': !config.affectCost,
                }"
              >
                {{ config.affectCost ? '是' : '否' }}
              </span>
            </td>
            <td>
              <div class="text-base-content/70">
                {{ config.description || '-' }}
              </div>
            </td>
            <td>
              <div class="flex items-center gap-1">
                <button
                  class="btn btn-ghost btn-xs btn-square"
                  title="编辑"
                  @click="emit('edit', config)"
                >
                  <span class="material-symbols-outlined icon-sm">edit</span>
                </button>
                <button
                  class="btn btn-ghost btn-xs btn-square text-error hover:bg-error/10"
                  title="删除"
                  @click="handleDelete(config)"
                >
                  <span class="material-symbols-outlined icon-sm">delete</span>
                </button>
              </div>
            </td>
          </tr>
        </template>

        <!-- 空状态 -->
        <TableEmptyState
          v-else
          :colspan="tableHeaders.length"
          title="暂无材料复用配置"
          description="还没有添加任何可周转材料的复用配置"
          icon="autorenew"
        />
      </tbody>
    </table>
  </div>
</template>
