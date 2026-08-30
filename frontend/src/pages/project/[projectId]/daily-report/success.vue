<script setup lang="ts">
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { useDailyReportStoreV2 } from '@/stores/report'

definePage({
  meta: { title: '提交成功' },
})

const router = useRouter()
const store = useDailyReportStoreV2()

function handleContinue() {
  store.reset()
  router.push('./import')
}

function goToHome() {
  store.reset()
  router.push('/')
}

onBeforeRouteLeave(() => {
  store.reset()
})
</script>

<template>
  <div class="p-6 pb-24 max-w-2xl mx-auto">
    <div class="panel p-6 text-center">
      <div
        class="w-20 h-20 rounded-full bg-success/10 flex items-center justify-center mx-auto mb-4"
      >
        <span class="material-symbols-outlined icon-2xl text-success">check_circle</span>
      </div>

      <h2 class="text-2xl font-semibold text-base-content mb-2">提交成功</h2>
      <p class="text-fg-subtle mb-4">日报数据已成功提交到系统</p>

      <div class="divider"></div>

      <div class="grid grid-cols-2 gap-4 mb-4">
        <div class="text-center">
          <div class="text-3xl font-semibold text-primary mb-1">
            {{ store.summaryStats.totalResources }}
          </div>
          <div class="text-sm text-fg-subtle">资源项数</div>
        </div>
        <div class="text-center">
          <div class="text-3xl font-semibold text-primary mb-1">
            {{ store.summaryStats.allocatedTasks }}
          </div>
          <div class="text-sm text-fg-subtle">分配工序</div>
        </div>
      </div>

      <div class="space-y-3">
        <button class="btn btn-primary btn-block" @click="handleContinue">
          <span class="material-symbols-outlined">replay</span>
          <span>继续处理新日报</span>
        </button>

        <button class="btn btn-ghost btn-block" @click="goToHome">
          <span class="material-symbols-outlined">home</span>
          <span>返回首页</span>
        </button>
      </div>
    </div>
  </div>
</template>
