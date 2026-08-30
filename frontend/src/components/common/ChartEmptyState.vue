<script setup lang="ts">
/**
 * ChartEmptyState - 图表（ECharts / 自定义可视化）的空 / 错误占位
 *
 * 与 TableEmptyState（用于 &lt;tr&gt;）区分：本组件用于占据整个 chart 区域。
 *
 * 用法：
 *   <ChartEmptyState
  import ChartEmptyState from '@/components/common/ChartEmptyState.vue' icon="bar_chart" title="暂无月度数据" />
 *   <ChartEmptyState
  import ChartEmptyState from '@/components/common/ChartEmptyState.vue' icon="error_outline" title="加载失败" color="error">
 *     <button class="btn btn-primary btn-sm" @click="refresh">重试</button>
 *   </ChartEmptyState>
 */
interface Props {
  /** Material Symbols 图标名，默认 inbox */
  icon?: string
  /** 主标题（必填） */
  title: string
  /** 副标题 / 提示 */
  description?: string
  /** 颜色变体：neutral（默认，无数据） / error（加载失败） / warning（数据异常） */
  variant?: 'neutral' | 'error' | 'warning'
}

const { icon = 'inbox', title, description, variant = 'neutral' } = defineProps<Props>()
</script>

<template>
  <div
    class="h-full min-h-40 w-full flex items-center justify-center bg-base-300/30 rounded-lg"
    role="status"
    :aria-label="title"
  >
    <div class="text-center px-6 py-8 max-w-xs">
      <div
        class="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-3"
        :class="{
          'bg-base-300': variant === 'neutral',
          'bg-error/10': variant === 'error',
          'bg-warning/10': variant === 'warning',
        }"
      >
        <span
          class="material-symbols-outlined icon-2xl"
          :class="{
            'text-base-content/30': variant === 'neutral',
            'text-error': variant === 'error',
            'text-warning': variant === 'warning',
          }"
          >{{ icon }}</span
        >
      </div>
      <p
        class="text-sm font-medium"
        :class="{
          'text-base-content/70': variant === 'neutral',
          'text-error': variant === 'error',
          'text-warning': variant === 'warning',
        }"
      >
        {{ title }}
      </p>
      <p v-if="description" class="text-xs text-fg-muted mt-1.5">{{ description }}</p>
      <div v-if="$slots.default" class="mt-4 flex justify-center gap-2">
        <slot />
      </div>
    </div>
  </div>
</template>
