<script setup lang="ts">
import { useDailyReportStoreV2 } from '@/stores/report'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { computed } from 'vue'
import { type TaskResp } from '@/client'

const store = useDailyReportStoreV2()
const { tasks } = useScheduleApi()

const taskMap = computed<Map<number, TaskResp>>(() => {
  const map = new Map()
  for (const task of tasks.value) {
    map.set(task.id, task)
  }
  return map
})

const groupedResources = computed<Map<string, { taskId: number; quantity: number }[]>>(() => {
  const map = new Map<string, { taskId: number; quantity: number }[]>()
  for (const usage of store.resourceUsages) {
    if (!map.has(usage.resourceName)) {
      map.set(usage.resourceName, [])
    }
    map.get(usage.resourceName)!.push({ taskId: usage.taskId, quantity: usage.quantity })
  }
  return map
})
</script>

<template>
  <div class="flex flex-col gap-2 mt-2 mb-2">
    <div
      v-for="[resourceName, usages] in groupedResources"
      :key="resourceName"
      class="card border border-base-300"
    >
      <div class="flex flex-row justify-between items-center p-4">
        <div class="flex items-center gap-4">
          <h3 class="font-medium text-base-content">
            {{ resourceName }}
          </h3>
          <!-- 分配该资源的任务 -->
          <div v-for="usage in usages" :key="usage.taskId">
            <div class="badge badge-primary opacity-80 gap-1">
              <span class="text-xs italic pr-2">
                {{ taskMap.get(usage.taskId)?.code }}
              </span>
              <span class="text-sm">{{ usage.quantity }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
