<script setup lang="ts">
/**
 * ThemeToggle - 主题模式选择器（自动 / 浅色 / 深色 三选一）
 *
 * 下拉显式列出三种模式并勾选当前项，点击前即可预知目标模式；
 * 点击外部或 Esc 收起，选择后写入 useTheme 的持久化偏好（localStorage）。
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { useTheme } from '@/composables/useTheme'
import type { ThemeMode } from '@/composables/useTheme'

const { mode, setMode } = useTheme()

interface ThemeOption {
  value: ThemeMode
  label: string
  icon: string
  hint: string
}

/** 三选一选项：自动（跟随系统）/ 浅色 / 深色 */
const OPTIONS: readonly ThemeOption[] = [
  { value: 'auto', label: '自动', icon: 'brightness_auto', hint: '跟随系统' },
  { value: 'starglass-light', label: '浅色', icon: 'light_mode', hint: '始终浅色' },
  { value: 'starglass', label: '深色', icon: 'dark_mode', hint: '始终深色' },
]

const ICONS: Record<ThemeMode, string> = {
  auto: 'brightness_auto',
  starglass: 'dark_mode',
  'starglass-light': 'light_mode',
}

const TITLES: Record<ThemeMode, string> = {
  auto: '自动模式（跟随系统）',
  starglass: '深色模式',
  'starglass-light': '浅色模式',
}

const open = ref(false)
const wrapEl = ref<HTMLElement | null>(null)

onClickOutside(wrapEl, () => (open.value = false))

function toggle() {
  open.value = !open.value
}

function choose(m: ThemeMode) {
  setMode(m)
  open.value = false
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    open.value = false
  }
}

watch(open, (isOpen) => {
  if (isOpen) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div ref="wrapEl" class="relative">
    <button
      type="button"
      class="theme-toggle btn-ghost-outline flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
      :title="TITLES[mode]"
      :aria-label="`主题模式：${TITLES[mode]}`"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="toggle"
    >
      <span class="material-symbols-outlined icon-md">{{ ICONS[mode] }}</span>
      <span class="material-symbols-outlined icon-sm text-fg-subtle" aria-hidden="true">
        expand_more
      </span>
    </button>

    <!-- 弹层：三选一显式选择（点外部 / Esc 收起） -->
    <div
      v-show="open"
      class="absolute right-0 top-[calc(100%+0.25rem)] z-[60] min-w-44 rounded-box bg-base-200 border border-base-content/10 shadow-xl overflow-hidden p-1"
      role="menu"
      aria-label="选择主题模式"
    >
      <button
        v-for="opt in OPTIONS"
        :key="opt.value"
        type="button"
        role="menuitemradio"
        :aria-checked="mode === opt.value"
        class="flex w-full items-center gap-2 rounded-field px-2.5 py-1.5 text-sm transition-colors"
        :class="
          mode === opt.value
            ? 'bg-primary/10 text-primary'
            : 'text-base-content hover:bg-base-content/5'
        "
        @click="choose(opt.value)"
      >
        <span class="material-symbols-outlined icon-sm" aria-hidden="true">{{ opt.icon }}</span>
        <span class="flex-1 text-left">{{ opt.label }}</span>
        <span class="text-xs text-fg-subtle">{{ opt.hint }}</span>
        <span
          v-if="mode === opt.value"
          class="material-symbols-outlined icon-sm"
          aria-hidden="true"
        >
          check
        </span>
      </button>
    </div>
  </div>
</template>
