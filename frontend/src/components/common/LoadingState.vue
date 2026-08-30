<script setup lang="ts">
/**
 * LoadingState - 统一加载状态（spinner / skeleton / inline）
 *
 * 取代散落在 ParetoSolutionsList / RunStatusBar / ProjectOverview 等处的 4 种
 * 不同加载视觉表达。
 *
 * - spinner：居中 spinner + 可选文案（用于整页加载）
 * - skeleton：骨架屏（用于 card / chart 占位）
 * - inline：小号行内 spinner（用于按钮 / 表单字段加载）
 */
interface Props {
  /**
   * 视觉变体
   * - spinner：居中 spinner（默认）
   * - skeleton：渲染 slot 的骨架版（父组件须传 skeleton 模板）
   * - inline：行内小 spinner
   */
  variant?: 'spinner' | 'skeleton' | 'inline'
  /** 加载提示文字（spinner / inline 有效） */
  text?: string
  /** 自定义类名（覆盖根容器样式） */
  class?: string
  /** spinner 大小（DaisyUI loading-md / loading-lg） */
  size?: 'sm' | 'md' | 'lg'
}

const { variant = 'spinner', text, class: rootClass = '', size = 'md' } = defineProps<Props>()

const sizeClass = {
  sm: 'loading-sm',
  md: 'loading-md',
  lg: 'loading-lg',
}[size]
</script>

<template>
  <!-- spinner：居中 -->
  <div
    v-if="variant === 'spinner'"
    class="flex flex-col items-center justify-center gap-3 py-8"
    :class="rootClass"
    role="status"
    :aria-label="text ?? '加载中'"
  >
    <span :class="['loading loading-spinner text-primary', sizeClass]" />
    <p v-if="text" class="text-sm text-fg-muted">{{ text }}</p>
  </div>

  <!-- skeleton：渲染父组件传入的 skeleton 模板 -->
  <div
    v-else-if="variant === 'skeleton'"
    :class="rootClass"
    role="status"
    aria-label="加载中"
    aria-busy="true"
  >
    <slot />
  </div>

  <!-- inline：行内小 spinner -->
  <span
    v-else-if="variant === 'inline'"
    class="inline-flex items-center gap-2"
    :class="rootClass"
    role="status"
    :aria-label="text ?? '加载中'"
  >
    <span :class="['loading loading-spinner text-primary', sizeClass]" />
    <span v-if="text" class="text-sm text-fg-muted">{{ text }}</span>
  </span>
</template>
