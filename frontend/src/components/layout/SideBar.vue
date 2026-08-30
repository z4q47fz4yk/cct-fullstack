<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSidebarNav, type NavItem } from '@/composables/useSidebarNav'

const route = useRoute()
const router = useRouter()
const { navItems, currentProjectName, isLoadingProject } = useSidebarNav()

const isActive = (item: NavItem): boolean => {
  // 利用 vue-router 的嵌套路由匹配：当前路由的 matched 链中包含 item 的 name 即视为激活
  return route.matched.some((r) => r.name === item.name)
}

const handleNavClick = (item: NavItem) => {
  router.push(item.to)
}

const expandedMenu = computed(() => {
  const item = navItems.value.find((i) => i.children?.length && isActive(i))
  return item?.name || null
})
</script>

<template>
  <aside class="w-fit h-screen flex flex-col shrink-0">
    <div class="h-12 flex items-center px-5 pt-6 pb-4">
      <span class="text-primary text-xl font-bold">icon</span>
    </div>

    <!-- 当前项目标识 -->
    <div
      v-if="currentProjectName"
      class="project-indicator px-5 py-2 cursor-pointer hover:bg-base-300/50 transition-all"
      @click="router.push('/')"
    >
      <div class="flex items-center gap-2 text-sm mt-1">
        <span class="material-symbols-outlined icon-sm text-primary">folder</span>
        <span v-if="isLoadingProject" class="skeleton h-4 w-24 rounded" aria-label="加载项目名称" />
        <span v-else class="font-medium">{{ currentProjectName }}</span>
        <span class="material-symbols-outlined icon-xs text-neutral-content ml-auto"
          >swap_horiz</span
        >
      </div>
    </div>

    <nav class="nav-menu flex-1 py-6 flex flex-col gap-2 overflow-y-auto scrollbar-thin">
      <div
        v-for="item in navItems"
        :key="item.name"
        :class="{ 'border-l-2 border-primary': isActive(item) }"
      >
        <div
          class="nav-item group flex items-center gap-3 px-4 h-11 border-none cursor-pointer transition-all duration-200"
          :class="[
            isActive(item) && !item.children
              ? 'bg-primary/10 border border-primary/20 text-primary'
              : 'text-neutral-content hover:bg-primary/6 hover:text-base-content',
          ]"
          @click="handleNavClick(item)"
        >
          <span
            class="material-symbols-outlined icon-lg"
            :class="
              isActive(item) ? 'text-primary' : 'text-neutral-content group-hover:text-base-content'
            "
          >
            {{ item.icon }}
          </span>
          <span class="text-sm font-medium">{{ item.label }}</span>
          <span
            v-if="item.children"
            class="material-symbols-outlined icon-sm ml-auto transition-transform duration-400 ease-out"
            :class="expandedMenu === item.name ? 'rotate-90' : 'rotate-0'"
          >
            chevron_right
          </span>
        </div>

        <!-- 内置子菜单：grid-rows 技巧实现展开/收起动画 -->
        <div
          class="submenu-wrapper min-h-0 grid transition-[grid-template-rows] duration-400 ease-in-out"
          :class="
            item.children && expandedMenu === item.name ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
          "
        >
          <div
            class="submenu flex flex-col gap-1 pl-4 overflow-hidden"
            :class="expandedMenu === item.name ? 'opacity-100' : 'opacity-0'"
          >
            <template v-if="item.groups">
              <template v-for="group in item.groups" :key="group.label">
                <p
                  v-if="group.label"
                  class="px-4 pt-3 pb-1 text-[10px] font-medium tracking-widest text-fg-subtle select-none"
                >
                  {{ group.label }}
                </p>
                <RouterLink
                  v-for="child in group.children"
                  :key="child.name"
                  :to="child.to"
                  class="submenu-item px-4 py-2 rounded-lg text-sm transition-all duration-200 flex items-center gap-2"
                  :class="
                    route.matched.some((r) => r.name === child.name)
                      ? 'text-primary'
                      : 'text-neutral-content hover:text-base-content'
                  "
                >
                  <span class="material-symbols-outlined icon-md">{{ child.icon }}</span>
                  <span>{{ child.label }}</span>
                </RouterLink>
              </template>
            </template>
            <RouterLink
              v-else
              v-for="child in item.children"
              :key="child.name"
              :to="child.to"
              class="submenu-item px-4 py-2 rounded-lg text-sm transition-all duration-200 flex items-center gap-2"
              :class="
                route.matched.some((r) => r.name === child.name)
                  ? 'text-primary'
                  : 'text-neutral-content hover:text-base-content'
              "
            >
              <span class="material-symbols-outlined icon-md">{{ child.icon }}</span>
              <span>{{ child.label }}</span>
            </RouterLink>
          </div>
        </div>
      </div>
    </nav>

    <div class="sidebar-footer px-5 pb-6">
      <slot name="footer" />
    </div>
  </aside>
</template>
