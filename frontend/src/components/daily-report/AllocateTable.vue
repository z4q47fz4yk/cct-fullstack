<script setup lang="ts">
import { useDailyReportStoreV2 } from '@/stores/report'
import { computed, ref, watch } from 'vue'
import type { ResourceMappingCreateItem } from '@/client'

const taskId = defineModel<number | null>('taskId')
const isAllocationValid = defineModel<boolean>('isAllocationValid', { default: true })

const store = useDailyReportStoreV2()
const mappingItems = computed(() => {
  return store.mappingDecision.filter((item) => item.action != 'SKIP')
})
const mappingItemsMap = computed(() => {
  return mappingItems.value.reduce(
    (acc, item) => {
      acc[item.resourceName] = item
      return acc
    },
    {} as Record<string, ResourceMappingCreateItem>,
  )
})
const resourceItems = computed(() => {
  const usedResourceQuantities = new Map()
  for (const item of store.resourceUsages) {
    // 其它任务已使用额度
    if (item.taskId == taskId.value) continue
    const quantity = usedResourceQuantities.get(item.resourceName) || 0
    usedResourceQuantities.set(item.resourceName, quantity + item.quantity)
  }
  return store.parsedResourceItems
    .filter((item) => mappingItemsMap.value[item.resourceName])
    .map((item) => ({
      ...item,
      // 可用额度
      quantity:
        mappingItemsMap.value[item.resourceName]!.quantity -
        (usedResourceQuantities.get(item.resourceName) || 0),
      resourceUnit:
        mappingItemsMap.value[item.resourceName]!.action == 'CREATE_NEW'
          ? mappingItemsMap.value[item.resourceName]!.newResource!.unit
          : item.resourceUnit,
    }))
})

const allocatedQuantity = computed<Record<string, number>>({
  get: () => {
    if (!taskId.value) return {} as Record<string, number>
    const tmp = store.allocatedResourceQuantities.get(taskId.value)
    if (tmp) return tmp
    else {
      const tmp = resourceItems.value.reduce(
        (acc, item) => {
          acc[item.resourceName] = 0
          return acc
        },
        {} as Record<string, number>,
      )
      store.allocatedResourceQuantities.set(taskId.value, tmp)
      return tmp
    }
  },
  set: (value) => {
    if (taskId.value) store.allocatedResourceQuantities.set(taskId.value, value)
  },
})

// 表单校验：当前工序的错误
const fieldErrors = ref<Record<string, string>>({})

function validateQuantity(resourceName: string, value: number): boolean {
  const item = resourceItems.value.find((i) => i.resourceName === resourceName)
  if (!item) return true

  if (value < 0) {
    fieldErrors.value[resourceName] = '分配数量不能为负'
    return false
  }
  if (value > item.quantity) {
    fieldErrors.value[resourceName] = `不能超过可用数量 ${item.quantity}`
    return false
  }
  fieldErrors.value[resourceName] = ''
  return true
}

// 验证所有工序的所有分配是否合法
function validateAll() {
  let valid = true
  // 先验证当前工序
  for (const item of resourceItems.value) {
    const q = allocatedQuantity.value[item.resourceName] ?? 0
    if (!validateQuantity(item.resourceName, q)) {
      valid = false
    }
  }
  // 再验证其它工序（不显示错误，只检查是否有负数）
  for (const [otherTaskId, quantities] of store.allocatedResourceQuantities.entries()) {
    if (otherTaskId === taskId.value) continue
    for (const q of Object.values(quantities) as number[]) {
      if (q < 0) {
        valid = false
        break
      }
    }
  }
  isAllocationValid.value = valid
}

watch(store.allocatedResourceQuantities, validateAll)

defineEmits<{
  submit: [typeof allocatedQuantity.value]
}>()
</script>

<template>
  <!--资源分配列表-->
  <div v-if="taskId" class="panel p-0 h-full overflow-hidden">
    <div class="h-full overflow-x-auto">
      <table class="table table-pin-rows h-full">
        <thead>
          <tr>
            <th>资源名称</th>
            <th class="table-num">分配量</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in resourceItems" :key="item.resourceName">
            <td>
              <div class="flex items-center gap-2">
                <span class="whitespace-nowrap">{{ item.resourceName }}</span>
                <span v-if="item.cargo" class="badge badge-sm badge-info whitespace-nowrap">
                  {{ item.cargo }}
                </span>
              </div>
            </td>
            <td>
              <div class="flex items-center justify-end gap-2">
                <span class="text-xs text-fg-subtle font-num shrink-0">
                  可用 {{ item.quantity }}
                </span>
                <label class="input w-28">
                  <input
                    type="number"
                    class="text-right font-num"
                    :min="0"
                    :max="item.quantity"
                    v-model.lazy.number="allocatedQuantity[item.resourceName]"
                    step="0.01"
                    :class="{ 'input-error': fieldErrors[item.resourceName] }"
                    @change="
                      () => {
                        validateQuantity(
                          item.resourceName,
                          allocatedQuantity[item.resourceName] ?? 0,
                        )
                        validateAll()
                      }
                    "
                  />
                  <span class="text-neutral-content text-xs shrink-0">{{ item.resourceUnit }}</span>
                </label>
                <span v-if="fieldErrors[item.resourceName]" class="text-xs text-error shrink-0">
                  {{ fieldErrors[item.resourceName] }}
                </span>
              </div>
            </td>
            <td>
              <div class="flex gap-2">
                <button
                  class="btn btn-xs btn-outline"
                  @click="() => (allocatedQuantity[item.resourceName] = 0)"
                >
                  清零
                </button>
                <button
                  class="btn btn-xs btn-outline btn-secondary"
                  @click="() => (allocatedQuantity[item.resourceName] = item.quantity)"
                >
                  全量
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
