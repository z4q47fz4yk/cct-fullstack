<script setup lang="ts">
import { computed } from 'vue'
import { appHref } from '../../../site.config'

/**
 * 「回到项目」链接组件 —— 文档深链上下文感知。
 *
 * 应用跳转文档时携带 projectId（如 docsHref('/guide/faq?projectId=123')），
 * 文档页在浏览器端读取 query 后渲染「回到项目 N」链接（应用 SPA 路由 /project/:id/schedule）。
 * 无 projectId 时渲染为空（文档保持静态，可独立访问）。
 */
const projectId = computed(() => {
  if (typeof window === 'undefined') return null
  const v = new URLSearchParams(window.location.search).get('projectId')
  return v && /^\d+$/.test(v) ? v : null
})

const href = computed(() =>
  projectId.value ? appHref(`/project/${projectId.value}/schedule`) : '',
)
</script>

<template>
  <a v-if="projectId && href" :href="href" target="_self" rel="noopener" class="back-to-project">
    回到项目 {{ projectId }}
  </a>
</template>

<style scoped>
.back-to-project {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 4px 0 8px;
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--vp-c-brand-1);
  background-color: var(--vp-c-brand-soft);
}
.back-to-project:hover {
  text-decoration: none;
  background-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-inverse);
}
</style>
