<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'
import type { ThemeMode } from '@/composables/useTheme'

const { mode, cycle } = useTheme()

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

const ROTATE: Record<ThemeMode, string> = {
  auto: 'rotate-90',
  starglass: 'rotate-0',
  'starglass-light': 'rotate-180',
}
</script>

<template>
  <button
    class="theme-toggle btn-ghost-outline flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
    :title="TITLES[mode]"
    :aria-label="TITLES[mode]"
    @click="cycle"
  >
    <span
      class="material-symbols-outlined icon-md transition-transform duration-300"
      :class="ROTATE[mode]"
    >
      {{ ICONS[mode] }}
    </span>
  </button>
</template>
