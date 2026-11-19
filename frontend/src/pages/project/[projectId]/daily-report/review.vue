<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import ReviewTable from '@/components/daily-report/ReviewTable.vue'
import ReportSteps from '@/components/daily-report/ReportSteps.vue'
import PageHead from '@/components/common/PageHead.vue'
import { useDailyReportStoreV2 } from '@/stores/report'

definePage({
  meta: {
    title: '核对资源',
    icon: 'fact_check',
    // 从侧边栏隐藏：日报向导仅从「资源使用量」页进入
    showInNav: false,
    parentName: '/project/[projectId]/daily-report',
    navOrder: 2,
  },
})

const router = useRouter()
const store = useDailyReportStoreV2()

// 统计
const stats = computed(() => {
  const total = store.mappingDecision.length
  const skipped = store.mappingDecision.filter((m) => m.action == 'SKIP').length
  const createNewCount = store.mappingDecision.filter((m) => m.action == 'CREATE_NEW').length

  return { total, skipped, createNewCount }
})

function goBack() {
  router.push('./import')
}

async function goToAllocate() {
  await store.confirmMapping()
  await router.push('./allocate')
}
</script>

<template>
  <div class="p-6 pb-24">
    <PageHead title="核对资源" subtitle="确认解析出的资源数据" />
    <div v-if="store.mappingDecision.length === 0" class="text-center py-8">
      <div
        class="w-20 h-20 rounded-full bg-base-200 flex items-center justify-center mx-auto mb-4 border border-base-300"
      >
        <span class="material-symbols-outlined icon-2xl text-base-content/30">description</span>
      </div>
      <p class="text-fg-subtle mb-4">暂无数据，请先导入日报文件</p>
      <button class="btn btn-primary" @click="goBack">
        <span class="material-symbols-outlined">upload_file</span>
        <span>去导入</span>
      </button>
    </div>

    <div v-else class="space-y-4">
      <ReportSteps :current="2" />
      <!-- 标题和统计 -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <h2 class="text-lg font-semibold text-base-content">核对资源数据</h2>
          <div class="flex items-center gap-2 text-sm">
            <span class="badge badge-sm">共 {{ stats.total }} 项</span>
            <span class="badge badge-success badge-sm">提交 {{ stats.total - stats.skipped }}</span>
            <span v-if="stats.createNewCount > 0" class="badge badge-info badge-sm">
              创建 {{ stats.createNewCount }} 个新资源
            </span>
            <span v-if="stats.skipped > 0" class="badge badge-neutral badge-sm">
              忽略 {{ stats.skipped }} 项
            </span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div class="card-title">解析数据核对</div></div>
        <ReviewTable></ReviewTable>

        <div class="card-body border-t border-base-300 flex flex-col items-end gap-3">
          <div v-if="store.error" class="alert alert-error alert-sm w-full" role="alert">
            <span class="material-symbols-outlined icon-sm">error</span>
            <span>{{ store.error }}</span>
          </div>
          <button class="btn btn-primary" :disabled="store.isLoading" @click="goToAllocate">
            <span v-if="store.isLoading" class="loading loading-spinner loading-xs"></span>
            <span v-else class="material-symbols-outlined">arrow_forward</span>
            <span>
              {{ store.isLoading ? '处理中...' : '提交 → 下一步：分配工序' }}
            </span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
