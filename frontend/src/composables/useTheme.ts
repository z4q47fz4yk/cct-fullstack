import { useStorage, usePreferredDark } from '@vueuse/core'
import { computed, watch } from 'vue'
import { refreshThemeColors } from '@/utils/themeColors'

type Theme = 'starglass' | 'starglass-light'

/**
 * 用户主题偏好：auto（跟随系统）｜ starglass（深色）｜ starglass-light（浅色）
 */
const stored = useStorage<Theme | 'auto'>('app-theme', 'auto')
const preferredDark = usePreferredDark()

/** 解析后的实际主题 */
const resolved = computed<Theme>(() => {
  if (stored.value === 'auto') {
    return preferredDark.value ? 'starglass' : 'starglass-light'
  }
  return stored.value
})

// 模块级 watcher — 首次 import 即执行，保证首屏正确
watch(
  resolved,
  (t) => {
    document.documentElement.dataset.theme = t
    refreshThemeColors()
  },
  { immediate: true },
)

export function useTheme() {
  const isDark = computed(() => resolved.value === 'starglass')

  function toggle() {
    stored.value = resolved.value === 'starglass' ? 'starglass-light' : 'starglass'
  }

  return { theme: resolved, isDark, toggle }
}
