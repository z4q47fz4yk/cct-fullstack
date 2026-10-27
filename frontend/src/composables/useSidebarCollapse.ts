import { useStorage } from '@vueuse/core'
import { computed } from 'vue'

/**
 * 侧边栏折叠状态（设计稿：底部「收起菜单」按钮，折叠为 64px 图标栏）。
 *
 * 模块级共享：SideBar（渲染 + 底部按钮）与 BasicLayout（顶栏同步布局）
 * 各自调用本 composable 读取同一状态。
 */
const stored = useStorage<boolean>('sidebar-collapsed', false)

export function useSidebarCollapse() {
  const collapsed = computed(() => stored.value)

  function toggle() {
    stored.value = !stored.value
  }

  return { collapsed, toggle }
}
