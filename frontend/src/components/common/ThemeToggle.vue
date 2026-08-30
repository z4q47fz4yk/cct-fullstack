<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'

const { isDark, toggle } = useTheme()
</script>

<template>
  <button
    class="theme-toggle btn-ghost-outline flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
    :title="isDark ? '切换到浅色模式' : '切换到深色模式'"
    @click="toggle"
  >
    <span
      class="material-symbols-outlined icon-md transition-transform duration-300"
      :class="isDark ? 'rotate-0' : 'rotate-180'"
    >
      {{ isDark ? 'dark_mode' : 'light_mode' }}
    </span>
  </button>
</template>
