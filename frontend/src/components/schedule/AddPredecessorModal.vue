<script setup lang="ts">
import { ref, computed } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import type { TaskResp, TaskSummary, DependencyType } from '@/client/types.gen'

const { currentTask, availableTasks } = defineProps<{
  currentTask: TaskResp | null
  availableTasks: TaskSummary[]
}>()

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  add: [payload: { predecessorId: number; type: DependencyType }]
}>()

// 内部状态
const searchQuery = ref('')
const selectedTaskId = ref<number | null>(null)
const dependencyType = ref<DependencyType>('FS')

// 依赖类型选项
const dependencyOptions: {
  value: DependencyType
  label: string
  description: string
}[] = [
  {
    value: 'FS',
    label: '完成-开始 (FS)',
    description: '前置任务完成后，后续任务才能开始（最常见）',
  },
  {
    value: 'SS',
    label: '开始-开始 (SS)',
    description: '两个任务同时开始',
  },
  {
    value: 'FF',
    label: '完成-完成 (FF)',
    description: '两个任务同时完成',
  },
]

// 过滤后的任务列表
const filteredTasks = computed(() => {
  if (!searchQuery.value.trim()) return availableTasks
  const query = searchQuery.value.toLowerCase()
  return availableTasks.filter(
    (task) => task.name.toLowerCase().includes(query) || task.code.toLowerCase().includes(query),
  )
})

// 当前选中的依赖类型说明
const currentTypeDescription = computed(() => {
  return dependencyOptions.find((opt) => opt.value === dependencyType.value)?.description || ''
})

// 是否可以添加
const canAdd = computed(() => selectedTaskId.value !== null)

// 选择任务
const selectTask = (taskId: number) => {
  selectedTaskId.value = taskId
}

// 关闭模态框
const closeModal = () => {
  open.value = false
  resetForm()
}

// 重置表单
const resetForm = () => {
  searchQuery.value = ''
  selectedTaskId.value = null
  dependencyType.value = 'FS'
}

// 添加依赖
const handleAdd = () => {
  if (selectedTaskId.value === null) return
  emit('add', {
    predecessorId: selectedTaskId.value,
    type: dependencyType.value,
  })
  closeModal()
}
</script>

<template>
  <BaseModal v-model:open="open" title="添加前置任务" class="max-w-md">
    <fieldset class="fieldset space-y-4">
      <!-- 搜索任务 -->
      <div>
        <legend class="fieldset-legend text-sm">选择前置任务</legend>
        <label class="input-bordered w-full">
          <span class="material-symbols-outlined text-fg-subtle">search</span>
          <input v-model="searchQuery" type="text" placeholder="搜索任务名称或编码" />
        </label>

        <!-- 任务列表 -->
        <div class="mt-2 max-h-40 overflow-y-auto border border-base-300 rounded-lg">
          <div v-if="filteredTasks.length === 0" class="p-4 text-center text-sm text-fg-subtle">
            没有找到可选择的任务
          </div>
          <div
            v-for="task in filteredTasks"
            :key="task.id"
            class="flex items-center gap-3 p-3 cursor-pointer hover:bg-base-200 transition-colors border-b border-base-300 last:border-b-0"
            :class="{ 'bg-primary/10': selectedTaskId === task.id }"
            @click="selectTask(task.id)"
          >
            <input
              type="radio"
              :checked="selectedTaskId === task.id"
              class="radio radio-primary radio-sm"
            />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="badge badge-primary badge-sm shrink-0">{{ task.code }}</span>
                <span class="font-medium truncate text-sm">{{ task.name }}</span>
              </div>
              <div class="text-xs text-fg-muted mt-0.5">{{ task.duration }}天</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 依赖类型选择 -->
      <div>
        <legend class="fieldset-legend text-sm">依赖类型</legend>
        <select v-model="dependencyType" class="select select-bordered w-full">
          <option v-for="opt in dependencyOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>

      <!-- 信息提示框 -->
      <div class="alert alert-soft alert-info text-sm">
        <span class="material-symbols-outlined text-info">info</span>
        <span>{{ currentTypeDescription }}</span>
      </div>
    </fieldset>

    <div class="modal-action">
      <button class="btn btn-ghost" @click="closeModal">取消</button>
      <button class="btn btn-primary" :disabled="!canAdd" @click="handleAdd">添加依赖</button>
    </div>
  </BaseModal>
</template>
