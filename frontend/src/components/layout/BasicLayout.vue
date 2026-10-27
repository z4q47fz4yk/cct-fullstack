<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import SideBar from './SideBar.vue'
import ProjectSwitcher from './ProjectSwitcher.vue'
import UserMenu from '@/components/common/UserMenu.vue'
import { useProjectContext } from '@/composables/useProjectContext'
import { docsHref } from '@site'

const route = useRoute()
const { isInProject } = useProjectContext()

// 面包屑：平台名 / 页面标题（设计稿顶栏）
const crumbs = computed(() => ['CCT 施工多目标优化平台', String(route.meta.title ?? '')])

// 文档站入口（L2 跨站导航）：指向同源 /docs/ 下的文档站
const docsUrl = docsHref('/guide/intro')
</script>

<template>
  <div class="layout flex h-screen w-screen overflow-hidden bg-transparent">
    <!-- 侧边栏（藏青深色，不随主题切换） -->
    <KeepAlive>
      <SideBar />
    </KeepAlive>

    <!-- 主内容区 -->
    <main class="main-content flex-1 flex flex-col min-w-200">
      <!-- 顶栏：面包屑 + 项目切换 + 操作区（设计稿白色 topbar） -->
      <header class="topbar shrink-0 h-14 flex items-center gap-4 px-5 border-b border-panel-border bg-panel">
        <nav class="crumbs flex items-center gap-1.5 text-sm text-fg-muted min-w-0" aria-label="面包屑">
          <template v-for="(c, i) in crumbs" :key="i">
            <span v-if="i > 0" class="text-fg-subtle">/</span>
            <span :class="i === crumbs.length - 1 ? 'text-base-content font-semibold' : 'truncate'">
              {{ c }}
            </span>
          </template>
        </nav>

        <div class="flex-1" />

        <!-- 项目切换（仅项目上下文） -->
        <ProjectSwitcher v-if="isInProject" />

        <!-- 文档站入口（L2 跨站导航）：指向同源 /docs/ 下的文档站 -->
        <a
          class="btn-ghost-outline flex items-center gap-1.5 h-9 px-3 rounded-lg text-sm"
          :href="docsUrl"
          target="_blank"
          title="查看使用文档"
        >
          <span class="material-symbols-outlined icon-md">menu_book</span>
          <span class="hidden md:inline">文档</span>
        </a>
        <UserMenu />
      </header>

      <!-- 主内容滚动区域 -->
      <div class="main-body flex-1 overflow-y-auto overflow-x-hidden p-4 scrollbar-thin">
        <slot />
      </div>
    </main>
  </div>
</template>

<style scoped>
.topbar {
  box-shadow: 0 1px 2px rgb(16 24 40 / 0.04);
}
</style>
