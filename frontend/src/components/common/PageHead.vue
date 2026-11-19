<script setup lang="ts">
/**
 * PageHead - 页头（设计稿 · Element 风格）
 *
 * 布局：左侧大标题（20px/700）+ 灰色副标题，右侧 toolbar 插槽放操作按钮组。
 * 全站页面统一使用，替代各页内联手写页头。
 *
 * 用法：
 *   <PageHead title="项目信息" subtitle="项目基本参数与建设概况">
 *     <button class="btn btn-primary">保存</button>
 *   </PageHead>
 */
defineProps<{
  /** 页面标题 */
  title: string
  /** 副标题（可选，灰色说明文字） */
  subtitle?: string
}>()
</script>

<template>
  <div class="page-head">
    <div class="min-w-0">
      <h1 class="page-title">{{ title }}</h1>
      <p v-if="subtitle" class="page-subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.default" class="toolbar">
      <slot />
    </div>
  </div>
</template>
