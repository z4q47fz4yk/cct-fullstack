<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSidebarNav, type NavItem } from '@/composables/useSidebarNav'
import { useSidebarCollapse } from '@/composables/useSidebarCollapse'
import ThemeToggle from '@/components/common/ThemeToggle.vue'

const route = useRoute()
const router = useRouter()
const { navItems, currentProjectName, isLoadingProject } = useSidebarNav()
const { collapsed, toggle } = useSidebarCollapse()

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
  <aside class="sidebar" :class="{ 'is-collapsed': collapsed }">
    <!-- 品牌标识（设计稿内嵌 SVG：CCT 字母 + 建筑轮廓，不依赖外部图片） -->
    <div class="logo">
      <svg
        class="platform-logo"
        viewBox="0 0 96 96"
        role="img"
        aria-label="CCT 施工多目标优化平台"
      >
        <rect x="3" y="3" width="90" height="90" rx="18" fill="#12264A" stroke="#285A89" stroke-width="2" />
        <path
          d="M22 43V25l17-9 17 9v18M56 43V30l17 8v5M30 28v5m9-9v9m9-5v5"
          fill="none"
          stroke="#22D3EE"
          stroke-width="4"
          stroke-linejoin="round"
        />
        <path d="M17 45h61" stroke="#409EFF" stroke-width="3" />
        <text x="48" y="76" text-anchor="middle" fill="#FFFFFF" font-family="Arial,Helvetica,sans-serif" font-size="30" font-weight="700" letter-spacing="1">CCT</text>
      </svg>
      <div class="logo-text">
        <div class="logo-title">CCT 施工多目标优化</div>
        <div class="logo-sub">工期 · 成本 · 碳排放</div>
      </div>
    </div>

    <!-- 当前项目标识 -->
    <div
      v-if="currentProjectName"
      class="project-indicator"
      :title="currentProjectName"
      @click="router.push('/')"
    >
      <span class="material-symbols-outlined icon-sm shrink-0 text-sidebar-active">folder</span>
      <span v-if="isLoadingProject" class="skeleton h-4 flex-1 rounded" aria-label="加载项目名称" />
      <span v-else class="truncate">{{ currentProjectName }}</span>
      <span class="material-symbols-outlined icon-xs ml-auto shrink-0 opacity-60">swap_horiz</span>
    </div>

    <nav class="nav flex-1 overflow-y-auto scrollbar-thin">
      <template v-for="item in navItems" :key="item.name">
        <!-- 顶级菜单项（无子菜单）：直接导航 -->
        <button
          v-if="!item.children"
          type="button"
          class="nav-item"
          :class="{ active: isActive(item) }"
          :title="item.label"
          @click="handleNavClick(item)"
        >
          <span class="material-symbols-outlined icon-lg shrink-0">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </button>

        <!-- 分组菜单项：点击跳转首个子页；激活组自动展开 -->
        <div v-else>
          <button
            type="button"
            class="nav-item"
            :class="{ active: isActive(item), open: expandedMenu === item.name }"
            :title="item.label"
            @click="handleNavClick(item)"
          >
            <span class="material-symbols-outlined icon-lg shrink-0">{{ item.icon }}</span>
            <span class="nav-label">{{ item.label }}</span>
            <span
              class="material-symbols-outlined icon-sm nav-arrow shrink-0"
              :class="expandedMenu === item.name ? 'rotate-180' : ''"
            >
              expand_more
            </span>
          </button>

          <div
            class="submenu-wrapper"
            :class="expandedMenu === item.name && !collapsed ? 'expanded' : ''"
          >
            <div class="submenu">
              <template v-if="item.groups">
                <template v-for="group in item.groups" :key="group.label">
                  <p v-if="group.label" class="stage-label">{{ group.label }}</p>
                  <RouterLink
                    v-for="child in group.children"
                    :key="child.name"
                    :to="child.to"
                    class="submenu-item"
                    :class="{ active: route.matched.some((r) => r.name === child.name) }"
                  >
                    <span class="truncate">{{ child.label }}</span>
                  </RouterLink>
                </template>
              </template>
              <RouterLink
                v-for="child in item.children"
                v-else
                :key="child.name"
                :to="child.to"
                class="submenu-item"
                :class="{ active: route.matched.some((r) => r.name === child.name) }"
              >
                <span class="truncate">{{ child.label }}</span>
              </RouterLink>
            </div>
          </div>
        </div>
      </template>
    </nav>

    <!-- 底部：主题切换 + 收起/展开菜单 -->
    <div class="sidebar-footer">
      <ThemeToggle class="theme-toggle-sidebar" />
      <button type="button" class="collapse-btn" :title="collapsed ? '展开菜单' : '收起菜单'" @click="toggle">
        <span
          class="material-symbols-outlined icon-sm transition-transform duration-200"
          :class="collapsed ? 'rotate-90' : '-rotate-90'"
        >
          chevron_left
        </span>
        <span class="nav-label">收起菜单</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
/* ── 侧边栏容器：设计稿藏青渐变（深浅主题均为深色导航） ── */
.sidebar {
  width: 232px;
  flex: 0 0 232px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(180deg, var(--color-sidebar-deep), var(--color-sidebar));
  color: var(--color-sidebar-text);
  transition: width 0.22s var(--ease-soft, ease);
}
.sidebar.is-collapsed {
  width: 64px;
  flex-basis: 64px;
}

/* ── 品牌标识 ── */
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 16px 14px;
  border-bottom: 1px solid var(--color-sidebar-border);
  flex-shrink: 0;
}
.platform-logo {
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  display: block;
}
.logo-text {
  min-width: 0;
}
.logo-title {
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  line-height: 1.25;
  white-space: nowrap;
}
.logo-sub {
  font-size: 11px;
  color: #6b7ca8;
  margin-top: 2px;
  white-space: nowrap;
}
.is-collapsed .logo {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
}
.is-collapsed .logo-text {
  display: none;
}

/* ── 当前项目标识 ── */
.project-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 10px 0;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s;
}
.project-indicator:hover {
  background: rgb(255 255 255 / 0.05);
  color: #fff;
}
.is-collapsed .project-indicator {
  justify-content: center;
  padding: 8px 0;
}
.is-collapsed .project-indicator > *:not(:first-child) {
  display: none;
}

/* ── 导航 ── */
.nav {
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--color-sidebar-text);
  font-size: 14px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  position: relative;
  transition:
    background-color 0.15s,
    color 0.15s;
}
.nav-item:hover {
  background: rgb(255 255 255 / 0.05);
  color: #fff;
}
.nav-item.active {
  background: linear-gradient(
    90deg,
    rgb(34 211 238 / 0.18),
    rgb(37 99 235 / 0.18)
  );
  color: #fff;
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: -10px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 2px;
  background: var(--color-sidebar-active);
}
.nav-arrow {
  margin-left: auto;
  opacity: 0.6;
  transition: transform 0.2s;
}

/* 折叠态：仅图标 */
.is-collapsed .nav-item {
  justify-content: center;
  padding: 0;
  gap: 0;
}
.is-collapsed .nav-label,
.is-collapsed .nav-arrow {
  display: none;
}

/* ── 子菜单 ── */
.submenu-wrapper {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.25s var(--ease-soft, ease-in-out);
}
.submenu-wrapper.expanded {
  grid-template-rows: 1fr;
}
.submenu {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.stage-label {
  padding: 10px 12px 4px 40px;
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.08em;
  color: #5f75b5;
  user-select: none;
}
/* 设计稿：二级菜单无圆点，文字与顶级菜单文字左对齐（padding-left: 40px） */
.submenu-item {
  display: flex;
  align-items: center;
  padding: 8px 12px 8px 40px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 400;
  color: var(--color-sidebar-text-dim);
  transition:
    background-color 0.15s,
    color 0.15s;
}
.submenu-item:hover {
  background: rgb(255 255 255 / 0.05);
  color: #fff;
}
.submenu-item.active {
  color: var(--color-sidebar-active);
  font-weight: 500;
}

/* ── 底部折叠按钮 ── */
.sidebar-footer {
  flex-shrink: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--color-sidebar-border);
}
.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid rgb(255 255 255 / 0.1);
  background: rgb(255 255 255 / 0.04);
  color: var(--color-sidebar-text);
  font-size: 13px;
  cursor: pointer;
  transition:
    background-color 0.15s,
    color 0.15s;
}
.collapse-btn:hover {
  background: rgb(255 255 255 / 0.08);
  color: #fff;
}
.is-collapsed .collapse-btn {
  padding: 9px 0;
}
.is-collapsed .collapse-btn .nav-label {
  display: none;
}

/* 主题切换：贴侧边栏底栏样式（深色底上的幽灵描边按钮） */
.theme-toggle-sidebar {
  width: 100%;
  justify-content: center;
  margin-bottom: 8px;
  border: 1px solid rgb(255 255 255 / 0.1);
  background: rgb(255 255 255 / 0.04);
  color: var(--color-sidebar-text);
}
.theme-toggle-sidebar:hover {
  background: rgb(255 255 255 / 0.08);
  color: #fff;
}
</style>
