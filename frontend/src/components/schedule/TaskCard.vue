<script setup lang="ts">
import type { TaskWithTagsResp } from '@/client/types.gen'
import type { TaskStatus } from '@/types/schedule'

const { task } = defineProps<{
  task: TaskWithTagsResp
}>()

defineEmits<{
  edit: [task: TaskWithTagsResp]
  delete: [task: TaskWithTagsResp]
  addPredecessor: [task: TaskWithTagsResp]
  removePredecessor: [task: TaskWithTagsResp, predecessorId: number]
}>()

function getStatus(completed: number): TaskStatus {
  if (completed >= 1) return 'completed'
  if (completed > 0) return 'in_progress'
  return 'pending'
}

function getStatusColor(status: TaskStatus): string {
  switch (status) {
    case 'completed':
      return 'success'
    case 'in_progress':
      return 'primary'
    default:
      return 'neutral'
  }
}

function getStatusText(status: TaskStatus): string {
  switch (status) {
    case 'completed':
      return '已完成'
    case 'in_progress':
      return '进行中'
    default:
      return '待开始'
  }
}

const status = getStatus(task.completed)
const statusColor = getStatusColor(status)
const statusText = getStatusText(status)
</script>

<template>
  <div class="panel panel-hover transition-all group">
    <div class="p-4">
      <!-- 头部: 代码 + 名称 -->
      <div class="flex items-start justify-between">
        <div class="flex items-center gap-2 min-w-0">
          <span class="badge badge-primary badge-sm shrink-0">{{ task.code }}</span>
          <h3 class="font-bold truncate" :class="{ 'text-error': task.isCritical }">
            {{ task.name }}
          </h3>
        </div>
        <div
          class="flex gap-1 shrink-0 ml-2 md:opacity-0 md:group-hover:opacity-100 transition-opacity"
        >
          <button class="btn btn-ghost btn-xs btn-square" @click="$emit('edit', task)">
            <span class="material-symbols-outlined icon-sm">edit</span>
          </button>
          <button class="btn btn-ghost btn-xs btn-square text-error" @click="$emit('delete', task)">
            <span class="material-symbols-outlined icon-sm">delete</span>
          </button>
        </div>
      </div>

      <!-- 元信息: 工期 + 关键路径标识 -->
      <div class="flex flex-wrap gap-3 text-xs text-fg-muted mt-2">
        <span class="flex items-center gap-1">
          <span class="material-symbols-outlined icon-sm">calendar_today</span>
          <span class="font-num">{{ task.duration }}</span
          >天
        </span>
        <span v-if="task.isCritical" class="flex items-center gap-1 text-error">
          <span class="material-symbols-outlined icon-sm">warning</span>
          关键路径
        </span>
      </div>

      <!-- 任务描述 -->
      <p v-if="task.description" class="text-sm text-base-content/70 mt-2 line-clamp-2">
        {{ task.description }}
      </p>

      <!-- 前置工序 -->
      <div class="flex flex-wrap gap-2 mt-3 pt-3 border-t border-base-300">
        <div
          v-for="predecessor in task.predecessors"
          :key="predecessor.id"
          class="badge badge-ghost badge-sm gap-1 pr-1"
        >
          <span class="material-symbols-outlined icon-xs">link</span>
          <span class="text-xs text-fg-subtle">{{ predecessor.type }}</span>
          {{ predecessor.code }}
          <button
            class="ml-1 hover:text-error transition-colors"
            @click="$emit('removePredecessor', task, predecessor.id)"
          >
            <span class="material-symbols-outlined icon-xs">close</span>
          </button>
        </div>
        <div class="grow"></div>
        <button
          class="btn btn-ghost btn-xs rounded-full border border-base-300 border-dashed text-[10px] px-2 h-5 min-h-0 hover:border-primary hover:text-primary hover:bg-primary/10 gap-1 normal-case"
          @click="$emit('addPredecessor', task)"
        >
          <span class="material-symbols-outlined scale-75">add</span>
          前置工序
        </button>
      </div>

      <!-- 进度条 -->
      <div class="flex items-center justify-between mt-3 pt-3 border-t border-base-300">
        <div class="flex items-center gap-2">
          <span
            class="w-2 h-2 rounded-full shrink-0"
            :class="{
              'bg-success': statusColor === 'success',
              'bg-primary': statusColor === 'primary',
              'bg-base-300': statusColor === 'neutral',
            }"
          >
          </span>
          <span
            class="text-xs font-medium uppercase"
            :class="{
              'text-success': statusColor === 'success',
              'text-primary': statusColor === 'primary',
              'text-neutral': statusColor === 'neutral',
            }"
            >{{ statusText }}</span
          >
        </div>
        <div class="flex items-center gap-2">
          <progress
            class="progress progress-primary w-24"
            :value="task.completed * 100"
            max="100"
          ></progress>
          <span class="text-xs font-medium w-10 text-right"
            >{{ Math.round(task.completed * 100) }}%</span
          >
        </div>
      </div>
    </div>
  </div>
</template>
