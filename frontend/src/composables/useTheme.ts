import { useStorage, usePreferredDark } from '@vueuse/core'
import { computed, watch } from 'vue'
import { refreshThemeColors } from '@/utils/themeColors'

/** 实际渲染主题：starglass（深色）｜ starglass-light（浅色） */
type Theme = 'starglass' | 'starglass-light'
/** 用户偏好模式：auto（跟随系统）｜ starglass（深色）｜ starglass-light（浅色） */
export type ThemeMode = Theme | 'auto'

/**
 * 用户主题偏好：auto（跟随系统）｜ starglass（深色）｜ starglass-light（浅色）
 */
const stored = useStorage<ThemeMode>('app-theme', 'auto')
const preferredDark = usePreferredDark()

/** 三态循环顺序：auto → 浅色 → 深色 → auto */
const CYCLE_ORDER: ThemeMode[] = ['auto', 'starglass-light', 'starglass']

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

  /** 三态循环：auto → 浅色 → 深色 → auto */
  function cycle() {
    const i = CYCLE_ORDER.indexOf(stored.value)
    stored.value = CYCLE_ORDER[(i + 1) % CYCLE_ORDER.length]
  }

  return { mode: stored, theme: resolved, isDark, cycle }
}
