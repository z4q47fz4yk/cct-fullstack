<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

definePage({
  meta: {
    title: '页面未找到',
    // 从侧边栏隐藏：404 兜底不在导航中展示
    showInNav: false,
  },
})

const route = useRoute()
const router = useRouter()

function goHome() {
  router.push('/')
}

function goBack() {
  // 历史可回退则回退，否则回首页
  if (window.history.length > 1) router.back()
  else goHome()
}
</script>

<template>
  <main class="min-h-screen flex items-center justify-center p-4">
    <section class="panel w-full max-w-md p-8 flex flex-col items-center text-center gap-5">
      <div
        class="w-20 h-20 rounded-full bg-base-200 flex items-center justify-center text-base-content/30"
      >
        <span class="material-symbols-outlined" style="font-size: 48px">explore_off</span>
      </div>

      <div class="flex flex-col gap-1">
        <h1 class="text-2xl font-semibold text-base-content">页面未找到</h1>
        <p class="text-sm text-neutral-content">访问的页面不存在，或当前部署未启用对应功能</p>
      </div>

      <div
        v-if="route.path !== '/'"
        class="w-full px-3 py-2 rounded-lg bg-base-200 border border-base-300 text-xs font-mono text-base-content/70 break-all"
      >
        {{ route.fullPath }}
      </div>

      <div class="flex flex-wrap items-center justify-center gap-2 w-full">
        <button class="btn btn-ghost btn-sm gap-1" @click="goBack">
          <span class="material-symbols-outlined icon-sm">arrow_back</span>
          <span>返回上一页</span>
        </button>
        <button class="btn btn-primary btn-sm gap-1" @click="goHome">
          <span class="material-symbols-outlined icon-sm">home</span>
          <span>返回首页</span>
        </button>
      </div>
    </section>
  </main>
</template>
