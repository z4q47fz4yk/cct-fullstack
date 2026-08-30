<script setup lang="ts">
/**
 * IconAction - 图标按钮统一封装
 *
 * 解决以下问题：
 * - 散落的 `btn-xs btn-square`（24px）远低于推荐触控目标 32-44px
 * - 仅靠 `title` 属性移动端不可见，必须有 `aria-label`
 * - 不同地方混用 ghost / primary / error，视觉不一致
 *
 * 默认尺寸 sm = 32px（DaisyUI btn-sm btn-square），达到触控目标底线；
 * 不影响 PC 视觉。
 */
interface Props {
  /** Material Symbols 图标名 */
  icon: string
  /** 无障碍标签（必填：title 在移动端不显示） */
  label: string
  /** 按钮尺寸：sm=32px / md=40px */
  size?: 'sm' | 'md'
  /** 视觉变体 */
  variant?: 'ghost' | 'primary' | 'error' | 'warning' | 'success' | 'neutral'
  /** 是否禁用 */
  disabled?: boolean
  /** 是否加载中（显示小 spinner） */
  loading?: boolean
}

const {
  icon,
  label,
  size = 'sm',
  variant = 'ghost',
  disabled = false,
  loading = false,
} = defineProps<Props>()

const emit = defineEmits<{
  click: [event: MouseEvent]
}>()

const sizeClass = {
  sm: 'btn-sm min-h-8 min-w-8',
  md: 'btn-md min-h-10 min-w-10',
}[size]

function handleClick(e: MouseEvent) {
  emit('click', e)
}
</script>

<template>
  <button
    type="button"
    :class="[
      'btn btn-square',
      sizeClass,
      {
        'btn-ghost': variant === 'ghost',
        'btn-primary': variant === 'primary',
        'btn-error': variant === 'error',
        'btn-warning': variant === 'warning',
        'btn-success': variant === 'success',
        'btn-neutral': variant === 'neutral',
      },
    ]"
    :disabled="disabled || loading"
    :aria-label="label"
    :title="label"
    @click="handleClick"
  >
    <span v-if="loading" class="loading loading-spinner loading-xs" />
    <span v-else class="material-symbols-outlined icon-md">{{ icon }}</span>
  </button>
</template>
