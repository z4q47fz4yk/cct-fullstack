<script setup lang="ts">
import { computed } from 'vue'
import { useInsightsStore } from '@/stores/insights'

const { runId } = defineProps<{
  runId: string
}>()

const store = useInsightsStore()

const statusLabel = computed(() => {
  switch (store.currentRunStatus) {
    case 'RUNNING':
      return '运行中'
    case 'PENDING':
      return '等待中'
    case 'SUCCESS':
      return '完成'
    case 'FAILURE':
      return '失败'
    default:
      return '未知'
  }
})
</script>

<template>
  <div class="panel">
    <div class="p-3">
      <div class="flex items-center justify-between gap-4">
        <!-- 左侧：状态 + ID -->
        <div class="flex items-center gap-3">
          <div
            class="w-8 h-8 rounded-full flex items-center justify-center"
            :class="store.isRunning ? 'bg-primary/20' : 'bg-base-300'"
          >
            <span
              class="material-symbols-outlined icon-sm"
              :class="store.isRunning ? 'text-primary animate-spin' : 'text-neutral-content'"
            >
              {{ store.isRunning ? 'progress_activity' : 'check_circle' }}
            </span>
          </div>
          <div>
            <p class="text-xs text-fg-muted">运行 ID</p>
            <p class="text-sm font-mono text-base-content/70">{{ runId.slice(0, 8) }}...</p>
          </div>
        </div>

        <!-- 进度条 + 百分比 -->
        <div class="flex-1 max-w-xs">
          <div class="flex justify-between text-xs text-fg-muted mb-1">
            <span>进度</span>
            <span>{{ store.progress }}%</span>
          </div>
          <progress
            class="progress"
            :class="store.isRunning ? 'progress-primary' : 'progress-success'"
            :value="store.progress"
            max="100"
          ></progress>
        </div>

        <!-- 状态标签 -->
        <div
          class="badge badge-sm"
          :class="{
            'badge-info': store.currentRunStatus === 'RUNNING',
            'badge-error': store.currentRunStatus === 'FAILURE',
            'badge-success': store.currentRunStatus === 'SUCCESS',
            'badge-neutral': store.currentRunStatus === 'PENDING',
          }"
        >
          {{ statusLabel }}
        </div>

        <!-- 停止按钮（仅运行中显示） -->
        <button
          v-if="store.isRunning"
          class="btn btn-ghost btn-sm text-error"
          @click="store.stopOptimization()"
        >
          <span class="material-symbols-outlined icon-sm">stop</span>
          停止
        </button>
      </div>
    </div>
  </div>
</template>
