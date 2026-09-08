<script setup lang="ts">
/**
 * StatCard - KPI 统计卡片（统一模板）
 *
 * 取代散落在 OptimizationConfig / EmissionAnalysisTab /
 * ResourceStats 等组件中的 createReusableTemplate 重复实现。
 *
 * 工程面板风格：扁平面板 + 小标签行 + 等宽大数值 + 单位。
 * 数值统一使用 font-num（等宽数字），千分位由父组件通过 fmt* 工具处理。
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
  /** 主色调（控制数值与图标颜色），默认 primary */
  color?: SemanticColor
  /** 加载中（显示 spinner） */
  loading?: boolean
  /** 数值大小：'default' = 32px，'sm' = 24px（用于密集布局） */
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
  <div class="panel p-3 min-w-0">
    <!-- 标题行：小图标 + label -->
    <div class="flex items-center gap-1.5 mb-1.5">
      <span
        v-if="icon"
        class="material-symbols-outlined icon-sm shrink-0"
        :class="{
          'text-primary': color === 'primary',
          'text-info': color === 'info',
          'text-success': color === 'success',
          'text-warning': color === 'warning',
          'text-error': color === 'error',
          'text-accel': color === 'accel',
          'text-neutral-content': color === 'neutral',
        }"
        >{{ icon }}</span
      >
      <span class="text-xs text-fg-muted truncate">{{ label }}</span>
    </div>

    <!-- 数值行 -->
    <p v-if="loading" class="loading loading-spinner loading-sm" />
    <div v-else class="flex items-baseline gap-1">
      <span v-if="prefix" class="text-sm text-fg-muted font-num shrink-0">{{ prefix }}</span>
      <span
        class="font-num font-semibold truncate"
        :class="[
          size === 'sm' ? 'text-2xl' : 'metric-value',
          {
            'text-primary': color === 'primary',
            'text-info': color === 'info',
            'text-success': color === 'success',
            'text-warning': color === 'warning',
            'text-error': color === 'error',
            'text-accel': color === 'accel',
            'text-neutral-content': color === 'neutral',
          },
        ]"
      >
        {{ value }}
      </span>
      <span v-if="unit" class="text-xs text-fg-muted shrink-0">{{ unit }}</span>
    </div>
  </div>
</template>
