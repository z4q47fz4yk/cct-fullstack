<script setup lang="ts">
import { useDailyReportStoreV2 } from '@/stores/report'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { computed, ref } from 'vue'
import { type TaskResp } from '@/client'
import BaseModal from '@/components/ui/BaseModal.vue'
const storeV2 = useDailyReportStoreV2()
const { tasks } = useScheduleApi()

const selectedTaskId = defineModel<number | null>('selectedTaskId')
const { disableAction = false } = defineProps<{
  disableAction: boolean
}>()

const showTaskPicker = ref(false)

const taskMap = computed<Map<number, TaskResp>>(() => {
  const map = new Map()
  for (const task of tasks.value) {
    map.set(task.id, task)
  }
  return map
})

/** 该工序已分配（数量 > 0）的资源项数 */
function allocCount(taskId: number): number {
  const quantities = storeV2.allocatedResourceQuantities.get(taskId)
  if (!quantities) return 0
  return Object.values(quantities).filter((q) => q > 0).length
}

function pickTask(id: number) {
  selectedTaskId.value = id
  showTaskPicker.value = false
}
</script>

<template>
  <div class="flex flex-col gap-2 mt-2 mb-2">
    <div
      v-for="[taskId, v] in storeV2.allocatedResourceQuantities"
      :key="taskId"
      class="card border transition-colors"
      :class="[
        selectedTaskId === taskId
          ? 'border-primary/40 bg-primary/5'
          : disableAction
            ? 'border-base-300'
            : 'border-base-300 cursor-pointer hover:border-primary/30 hover:bg-base-200/40',
      ]"
      :role="disableAction ? undefined : 'button'"
      :tabindex="disableAction ? undefined : 0"
      :aria-pressed="selectedTaskId === taskId || undefined"
      :aria-label="
        disableAction ? undefined : `编辑工序 ${taskMap.get(taskId)?.name ?? taskId} 的分配`
      "
      @click="!disableAction && (selectedTaskId = taskId)"
      @keydown.enter="!disableAction && (selectedTaskId = taskId)"
      @keydown.space.prevent="!disableAction && (selectedTaskId = taskId)"
    >
      <div class="flex flex-row justify-between items-center p-4">
        <div class="flex flex-wrap items-center gap-4">
          <h3 class="font-medium text-base-content flex items-center">
            <span class="badge badge-soft badge-sm italic">
              {{ taskMap.get(taskId)?.code }}
            </span>
            {{ taskMap.get(taskId)?.name }}
          </h3>
          <!-- 分配给任务的资源 -->
          <div
            v-for="(quantity, resourceName) in v"
            :class="{ hidden: !quantity }"
            :key="resourceName"
          >
            <div class="badge badge-primary opacity-80 gap-1">
              <span class="text-sm">{{ resourceName }}</span>
              <span class="text-sm">{{ quantity }}</span>
            </div>
          </div>
        </div>
        <!-- 操作按钮 -->
        <div v-if="!disableAction" class="flex justify-end gap-2">
          <button
            @click.stop="
              () => {
                if (selectedTaskId == taskId) selectedTaskId = null
                storeV2.allocatedResourceQuantities.delete(taskId)
              }
            "
            class="btn btn-error btn-xs material-symbols-outlined icon-xs"
          >
            delete
          </button>
        </div>
      </div>
    </div>

    <!-- 添加入口：分配给工序 -->
    <div
      v-if="!disableAction"
      class="card border-2 border-dashed border-base-300 cursor-pointer hover:border-primary/50 hover:bg-base-200/50 transition-colors"
      role="button"
      :aria-label="'选择工序'"
      @click="showTaskPicker = true"
    >
      <div class="p-4 flex items-center justify-center gap-2 text-fg-subtle">
        <span class="material-symbols-outlined">add_circle</span>
        <span class="text-sm">分配给工序</span>
      </div>
    </div>
  </div>

  <!-- 工序选择弹窗 -->
  <BaseModal v-model:open="showTaskPicker" title="选择工序">
    <ul v-if="tasks.length > 0" class="list">
      <li
        v-for="task in tasks"
        :key="task.id"
        class="list-row"
        :class="{ active: task.id === selectedTaskId }"
        @click="pickTask(task.id)"
      >
        <span class="badge badge-primary badge-sm">{{ task.code }}</span>
        <span class="flex-1 min-w-0 truncate">{{ task.name }}</span>
        <span v-if="allocCount(task.id) > 0" class="text-xs text-fg-subtle font-num shrink-0">
          已分配 {{ allocCount(task.id) }} 项
        </span>
      </li>
    </ul>
    <p v-else class="text-center py-8 text-sm text-fg-subtle">暂无工序，请先在「任务管理」中创建</p>
  </BaseModal>
</template>
