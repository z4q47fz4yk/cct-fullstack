<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useDailyReportStoreV2 as useDailyReportStore } from '@/stores/report'

const router = useRouter()
const route = useRoute()
const store = useDailyReportStore()

const projectId = computed(() => (route.params as { projectId?: string }).projectId)

interface Step {
  key: string
  path: string
  label: string
  icon: string
  description: string
}

const steps = computed<Step[]>(() => {
  const prefix = projectId.value ? `/project/${projectId.value}/daily-report` : '/daily-report'
  return [
    {
      key: 'import',
      path: `${prefix}/import`,
      label: '导入日报',
      icon: 'upload_file',
      description: '上传并解析日报文件',
    },
    {
      key: 'review',
      path: `${prefix}/review`,
      label: '核对资源',
      icon: 'fact_check',
      description: '确认资源映射关系',
    },
    {
      key: 'allocate',
      path: `${prefix}/allocate`,
      label: '分配工序',
      icon: 'assignment',
      description: '分配资源到工序',
    },
    {
      key: 'confirm',
      path: `${prefix}/confirm`,
      label: '确认提交',
      icon: 'check_circle',
      description: '核对并提交数据',
    },
  ]
})

const currentStepIndex = computed(() => store.currentStepIndex)

const canNavigateToStep = (stepIndex: number): boolean => {
  return store.canNavigateToStep(stepIndex)
}

const navigateToStep = (step: Step, index: number) => {
  if (canNavigateToStep(index)) {
    router.push(step.path)
  }
}

const getStepStatus = (index: number): 'completed' | 'current' | 'pending' => {
  if (index < currentStepIndex.value) return 'completed'
  if (index === currentStepIndex.value) return 'current'
  return 'pending'
}

// 统计信息
const stats = computed(() => {
  const resourceCount = store.parsedResourceItems.length
  const allocatedTaskCount =
    store.resourceUsages.length > 0 ? new Set(store.resourceUsages.map((u) => u.taskId)).size : 0
  return { resourceCount, allocatedTaskCount }
})
</script>

<template>
  <div class="steps-nav flex flex-col gap-1">
    <div
      v-for="(step, index) in steps"
      :key="step.key"
      class="step-item group relative"
      :class="{ 'cursor-pointer': canNavigateToStep(index) }"
      @click="navigateToStep(step, index)"
    >
      <!-- 步骤项 -->
      <div
        class="step-content flex items-start gap-3 px-4 py-3 rounded-xl transition-all duration-200"
        :class="[
          getStepStatus(index) === 'current'
            ? 'bg-primary/10 border border-primary/30'
            : getStepStatus(index) === 'completed'
              ? 'bg-base-300/50 hover:bg-base-300'
              : 'opacity-50',
        ]"
      >
        <!-- 步骤图标/序号 -->
        <div
          class="step-icon w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-all"
          :class="[
            getStepStatus(index) === 'current'
              ? 'bg-primary text-primary-content'
              : getStepStatus(index) === 'completed'
                ? 'bg-success/20 text-success'
                : 'bg-base-300 text-neutral-content',
          ]"
        >
          <span
            v-if="getStepStatus(index) === 'completed'"
            class="material-symbols-outlined icon-sm"
          >
            check
          </span>
          <span v-else class="material-symbols-outlined icon-sm">{{ step.icon }}</span>
        </div>

        <!-- 步骤信息 -->
        <div class="step-info flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span
              class="text-sm font-medium"
              :class="getStepStatus(index) === 'current' ? 'text-primary' : 'text-base-content'"
            >
              {{ step.label }}
            </span>
            <span
              v-if="index === 1 && stats.resourceCount > 0"
              class="badge badge-sm badge-primary"
            >
              {{ stats.resourceCount }}
            </span>
            <span
              v-if="index === 2 && stats.allocatedTaskCount > 0"
              class="badge badge-sm badge-primary"
            >
              {{ stats.allocatedTaskCount }}
            </span>
          </div>
          <p class="text-xs text-neutral-content mt-0.5">{{ step.description }}</p>
        </div>
      </div>

      <!-- 连接线下一步骤的线 -->
      <div
        v-if="index < steps.length - 1"
        class="step-line absolute left-8 top-12 w-0.5 h-4"
        :class="getStepStatus(index) === 'completed' ? 'bg-success/50' : 'bg-base-300'"
      />
    </div>
  </div>
</template>

<style scoped>
.step-line {
  min-height: 16px;
}
</style>
