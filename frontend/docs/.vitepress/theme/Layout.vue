<script setup lang="ts">
import { computed } from 'vue'
import DefaultTheme from 'vitepress/theme'
import { useData } from 'vitepress'
import { appHref } from '../../../site.config'

// themeConfig.appBase 为自定义字段（docs/.vitepress/config.ts 中注入），
// 用于在导航栏渲染「打开系统」入口，全程不硬编码域名
const { theme } = useData()
const appBase = computed(() => {
  const base = (theme.value as { appBase?: string }).appBase
  return appHref(base ?? '/')
})
</script>

<template>
  <DefaultTheme.Layout>
    <template #nav-bar-content-after>
      <a class="app-entry" :href="appBase" target="_self" rel="noopener">打开系统</a>
    </template>
  </DefaultTheme.Layout>
</template>

<style scoped>
.app-entry {
  display: inline-flex;
  align-items: center;
  margin-left: 12px;
  padding: 4px 14px;
  border-radius: 8px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  border: 1px solid var(--vp-c-brand-1);
  transition:
    background-color 0.2s,
    color 0.2s;
  white-space: nowrap;
}
.app-entry:hover {
  background-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-inverse);
}
</style>
