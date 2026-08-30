<script setup lang="ts">
import { computed } from 'vue'
import { appHref } from '../../../site.config'

const props = defineProps<{ to: string }>()

// 指向应用的路由路径（如 /project/1/schedule）
// target="_self" 显式声明，避免被 VitePress 全局 click 拦截当成站内链接做 SPA 跳转
const href = computed(() => appHref(props.to))
</script>

<template>
  <a :href="href" target="_self" rel="noopener">
    <slot />
  </a>
</template>
