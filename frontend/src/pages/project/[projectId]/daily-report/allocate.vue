<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import AllocateTable from '@/components/daily-report/AllocateTable.vue'
import { useDailyReportStoreV2 } from '@/stores/report'
import AllocationByTask from '@/components/daily-report/AllocationByTask.vue'

definePage({
  meta: {
    title: '分配工序',
    icon: 'assignment',
    showInNav: true,
    parentName: '/project/[projectId]/daily-report',
    navOrder: 3,
  },
})

const router = useRouter()
const storeV2 = useDailyReportStoreV2()

const selectedTaskId = ref<number | null>(null)
const isAllocationValid = ref(true)

// 数据未就绪引导:仅用于主体显示说明,不进行自动跳转
type BlockInfo = { title: string; description: string; target: string; label: string } | null
const blockInfo = computed<BlockInfo>(() => {
  if (!storeV2.batchId || storeV2.parsedResourceItems.length === 0) {
    return {
      title: '尚未导入日报',
      description: '分配前需要先在导入日报页面上传文件并解析。',
      target: './import',
      label: '导入日报',
    }
  }
  if (storeV2.currentPhase === 'PENDING') {
    return {
      title: '请先完成资源核对',
      description: '分配前需要先在资源核对页面确认资源映射关系。',
      target: './review',
      label: '资源核对',
    }
  }
  return null
})

const isReadyToAllocate = computed(() => blockInfo.value === null)
const blockTitle = computed(() => blockInfo.value?.title ?? '')
const blockDescription = computed(() => blockInfo.value?.description ?? '')
const guideTarget = computed(() => blockInfo.value?.target ?? '')
const guideLabel = computed(() => blockInfo.value?.label ?? '')

function goToGuide() {
  if (guideTarget.value) router.push(guideTarget.value)
}

async function goToConfirm() {
  await storeV2.allocateResources()
  await router.push('./confirm')
}
</script>

<template>
  <div class="p-6 pb-24 max-w-6xl mx-auto">
    <!-- 数据未就绪:大空白态 -->
    <div v-if="!isReadyToAllocate" class="text-center py-8">
      <div
        class="w-20 h-20 rounded-full bg-base-200 flex items-center justify-center mx-auto mb-4 border border-base-300"
      >
        <span class="material-symbols-outlined icon-2xl text-base-content/30">pending_actions</span>
      </div>
      <h3 class="text-lg font-semibold text-base-content/70 mb-2">{{ blockTitle }}</h3>
      <p class="text-fg-subtle mb-4">{{ blockDescription }}</p>
      <button class="btn btn-primary" @click="goToGuide">
        <span class="material-symbols-outlined">arrow_forward</span>
        <span>前往 {{ guideLabel }}</span>
      </button>
    </div>

    <!-- 数据已就绪:正常内容 -->
    <div v-else class="space-y-4">
      <AllocationByTask v-model:selected-task-id="selectedTaskId" :disable-action="false" />

      <AllocateTable
        v-model:task-id="selectedTaskId"
        v-model:is-allocation-valid="isAllocationValid"
      />

      <!-- 未选择工序提示 -->
      <div v-if="!selectedTaskId" class="panel p-6 text-center">
        <div
          class="w-16 h-16 rounded-full bg-base-300 flex items-center justify-center mx-auto mb-3"
        >
          <span class="material-symbols-outlined icon-xl text-fg-subtle">touch_app</span>
        </div>
        <p class="text-fg-subtle">请从上方选择一个工序开始分配资源</p>
      </div>

      <div v-if="storeV2.error" class="alert alert-error alert-sm" role="alert">
        <span class="material-symbols-outlined icon-sm">error</span>
        <span>{{ storeV2.error }}</span>
      </div>

      <div class="pt-4">
        <button
          class="btn btn-primary btn-block"
          :disabled="storeV2.isLoading || !isAllocationValid"
          @click="goToConfirm"
        >
          <span v-if="storeV2.isLoading" class="loading loading-spinner loading-xs"></span>
          <span v-else class="material-symbols-outlined">arrow_forward</span>
          <span>{{ storeV2.isLoading ? '处理中...' : '下一步：确认提交' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
