<script setup lang="ts" generic="T extends string">
/**
 * SegmentControl - 玻璃风 segmented control 通用组件
 *
 * 用于 2-5 个互斥选项的快速切换。泛型 T 约束为 string，
 * 覆盖 UsageType / TabKey 等典型 string literal union 场景。
 *
 * 默认 role=tablist，按 WAI-ARIA tablist 行为：roving tabindex +
 * ArrowLeft/Right 循环切换。需要 radio 语义时传 role="radiogroup"，
 * 内部按钮会切换为 role="radio" + aria-checked。
 */
import { useId } from 'vue'

export interface SegmentOption<T extends string> {
  /** 选项值（与 v-model 类型一致） */
  value: T
  /** 显示文本（中文） */
  label: string
  /** Material Symbols 图标名（可选） */
  icon?: string
  /** 禁用该选项（仍可见不可点） */
  disabled?: boolean
}

interface Props {
  /** 当前选中值 */
  modelValue: T
  /** 选项列表（2-5 个） */
  options: ReadonlyArray<SegmentOption<T>>
  /** 容器尺寸：sm=32px, md=40px；默认 sm */
  size?: 'sm' | 'md'
  /** 无障碍标签 */
  ariaLabel?: string
  /** 占满父容器宽度（按比例均分） */
  fullWidth?: boolean
  /** 容器 ARIA role：tablist（默认）/ radiogroup / group */
  role?: 'tablist' | 'radiogroup' | 'group'
}

const {
  modelValue,
  options,
  size = 'sm',
  ariaLabel,
  fullWidth = false,
  role = 'tablist',
} = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: T]
}>()

const groupId = useId()

function isActive(v: T) {
  return v === modelValue
}

function select(opt: SegmentOption<T>) {
  if (opt.disabled) return
  if (opt.value !== modelValue) emit('update:modelValue', opt.value)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
  const enabled = options.filter((o) => !o.disabled)
  if (enabled.length < 2) return
  e.preventDefault()
  const idx = enabled.findIndex((o) => o.value === modelValue)
  if (idx < 0) return
  const next =
    e.key === 'ArrowRight'
      ? (idx + 1) % enabled.length
      : (idx - 1 + enabled.length) % enabled.length
  const target = enabled[next]
  if (target) emit('update:modelValue', target.value)
}
</script>

<template>
  <div
    :id="groupId"
    :role="role"
    :aria-label="ariaLabel"
    :aria-orientation="role === 'tablist' ? 'horizontal' : undefined"
    class="segment-control inline-flex items-center gap-[2px] rounded-lg bg-base-content/5 p-[3px] transition-colors duration-200"
    :class="[size === 'md' ? 'h-10' : 'h-9', fullWidth ? 'flex w-full' : '']"
    @keydown="onKeydown"
  >
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      :role="role === 'radiogroup' ? 'radio' : 'tab'"
      :tabindex="isActive(opt.value) ? 0 : -1"
      :aria-selected="role !== 'radiogroup' ? isActive(opt.value) : undefined"
      :aria-checked="role === 'radiogroup' ? isActive(opt.value) : undefined"
      :disabled="opt.disabled"
      class="segment-btn inline-flex flex-1 items-center justify-center gap-1.5 rounded-[7px] px-3 text-[13px] font-medium transition-all duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-40"
      :class="[
        size === 'md' ? 'h-[34px]' : 'h-[30px]',
        isActive(opt.value)
          ? 'bg-panel text-primary shadow-[0_1px_3px_rgb(16_24_40_/_0.1)]'
          : 'text-fg-muted hover:text-base-content',
      ]"
      @click="select(opt)"
    >
      <span v-if="opt.icon" class="material-symbols-outlined icon-sm" aria-hidden="true">
        {{ opt.icon }}
      </span>
      <span class="whitespace-nowrap">{{ opt.label }}</span>
    </button>
  </div>
</template>
