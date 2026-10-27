<script setup lang="ts">
/**
 * StatCard - KPI 统计卡片（设计稿 · Element 风格）
 *
 * 布局：左侧 42px 圆角图标块（语义色软底）+ 右侧标签行 + 等宽大数值。
 * 数值统一使用 font-num（等宽数字），千分位由父组件通过 fmt* 工具处理。
 * 主数值使用前景色（设计稿 value 为深色），语义色只体现在图标块上。
 *
 * 注意：颜色类必须用对象语法显式列出，Tailwind 编译期无法识别
 * 运行时拼接的字符串（如 `text-${color}`）。
 */
type SemanticColor = 'primary' | 'info' | 'success' | 'warning' | 'error' | 'neutral' | 'accel'
interface Props {
  /** 标签文字 */
  label: string
  /** 主数值（数字 / 字符串均可；千分位由父组件自行处理） */
  value: string | number
  /** 单位（如 "kg"、"天"、"个"），可选 */
  unit?: string
  /** Material Symbols 图标名（可选） */
  icon?: string
  /** 图标块语义色，默认 primary */
  color?: SemanticColor
  /** 加载中（显示 spinner） */
  loading?: boolean
  /** 数值大小：'default' = 22px，'sm' = 18px（用于密集布局） */
  size?: 'default' | 'sm'
  /** 货币前缀（如 "¥"），会显示在 value 之前 */
  prefix?: string
}

const {
  label,
  value,
  unit,
  icon,
  color = 'primary',
  loading = false,
  size = 'default',
  prefix,
} = defineProps<Props>()
</script>

<template>
  <div class="panel p-4 flex items-center gap-3.5 min-w-0">
    <!-- 图标块：42px 圆角软底 -->
    <div
      v-if="icon"
      class="w-10 h-10 rounded-[10px] flex items-center justify-center shrink-0"
      :class="{
        'bg-primary/10 text-primary': color === 'primary',
        'bg-info/10 text-info': color === 'info',
        'bg-success/10 text-success': color === 'success',
        'bg-warning/10 text-warning': color === 'warning',
        'bg-error/10 text-error': color === 'error',
        'bg-accel/10 text-accel': color === 'accel',
        'bg-base-300/60 text-fg-muted': color === 'neutral',
      }"
    >
      <span class="material-symbols-outlined icon-xl">{{ icon }}</span>
    </div>

    <div class="min-w-0">
      <!-- 标签行 -->
      <div class="text-[13px] text-fg-muted truncate">{{ label }}</div>

      <!-- 数值行 -->
      <p v-if="loading" class="loading loading-spinner loading-sm" />
      <div v-else class="flex items-baseline gap-1 mt-0.5">
        <span v-if="prefix" class="text-sm text-fg-muted font-num shrink-0">{{ prefix }}</span>
        <span
          class="font-num font-bold text-base-content truncate"
          :class="size === 'sm' ? 'text-lg' : 'text-[22px] leading-tight'"
        >
          {{ value }}
        </span>
        <span v-if="unit" class="text-xs text-fg-muted shrink-0">{{ unit }}</span>
      </div>

      <!-- 附加行（趋势 / 说明，可选） -->
      <div v-if="$slots.default" class="text-xs text-fg-subtle mt-0.5">
        <slot />
      </div>
    </div>
  </div>
</template>
