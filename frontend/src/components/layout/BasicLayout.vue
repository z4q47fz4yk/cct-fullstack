<script setup lang="ts">
import { useRoute } from 'vue-router'
import SideBar from './SideBar.vue'
import ThemeToggle from '@/components/common/ThemeToggle.vue'
import UserMenu from '@/components/common/UserMenu.vue'
import { docsHref } from '@site'

const route = useRoute()

// 文档站入口（L2 跨站导航）：指向同源 /docs/ 下的文档站
const docsUrl = docsHref('/guide/intro')
</script>

<template>
  <div class="layout flex h-screen w-screen overflow-hidden bg-transparent">
    <!-- 侧边栏 -->
    <KeepAlive>
      <SideBar />
    </KeepAlive>

    <!-- 主内容区 -->
    <main class="main-content flex-1 flex flex-col min-w-200">
      <!-- 头部区域 -->
      <header
        class="pt-8 min-h-12 h-fit shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-base-300/40"
      >
        <div class="header-title flex flex-col gap-0.5">
          <h1 class="text-base font-semibold text-base-content">{{ route.meta.title }}</h1>
          <p v-if="route.meta.description" class="text-xs text-neutral-content">
            {{ route.meta.description }}
          </p>
        </div>

        <!-- 由具体页面通过 Teleport 投送 header-actions -->
        <div id="header-actions" class="header-actions flex items-center gap-2">
          <!-- 文档站入口（同源 /docs/，L2 跨站导航） -->
          <a
            class="btn-ghost-outline flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
            :href="docsUrl"
            target="_blank"
            title="查看使用文档"
          >
            <span class="material-symbols-outlined icon-md">menu_book</span>
            <span class="hidden md:inline">文档</span>
          </a>
          <ThemeToggle />
          <UserMenu />
        </div>
      </header>

      <!-- 主内容滚动区域 -->
      <div class="main-body flex-1 overflow-y-auto overflow-x-hidden p-4 scrollbar-thin">
        <slot />
      </div>
    </main>
  </div>
</template>
