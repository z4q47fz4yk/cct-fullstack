<script setup lang="ts">
/**
 * BaseModal - 统一模态框（原生 <dialog> 派）
 *
 * 行为（浏览器原生免费提供）：
 *   - 打开：showModal() → 背景 inert（无法交互）+ 首次焦点管理
 *   - Esc 关闭：原生 cancel 事件（closeOnEscape=false 时阻止）
 *   - 遮罩点击关闭：dialog 自身点击（target === dialog）
 *   - 关闭后焦点归还给触发元素
 * 关闭时总是同步 update:open(false) 并 emit('close')。
 *
 * 用法：
 *   <BaseModal v-model:open="show" title="标题" class="max-w-lg">
 *     内容
 *     <template #actions>
 *       <button class="btn btn-primary">确定</button>
 *     </template>
 *   </BaseModal>
 * class 与其余 attrs 透传到 modal-box（如 max-w-*）。
 */
import { nextTick, ref, watch } from 'vue'

defineOptions({ inheritAttrs: false })

// Vue 3.5+ Reactive Props Destructure：解构即响应式，默认值在解构处声明。
const {
  title,
  closeOnOverlay = true,
  closeOnEscape = true,
} = defineProps<{
  title?: string
  /** 点击遮罩是否关闭，默认 true */
  closeOnOverlay?: boolean
  /** Esc 是否关闭，默认 true */
  closeOnEscape?: boolean
}>()

const emit = defineEmits<{ close: [] }>()

const open = defineModel<boolean>('open', { required: true })
const dialogEl = ref<HTMLDialogElement | null>(null)

function closeModal() {
  if (!open.value) return
  open.value = false
  emit('close')
}

/** 遮罩点击：点击 dialog 自身（modal-box 之外）即遮罩 */
function onClick(e: MouseEvent) {
  if (closeOnOverlay && e.target === dialogEl.value) closeModal()
}

function onCancel(e: Event) {
  if (!closeOnEscape) e.preventDefault()
}

/** 原生关闭（Esc / close()）后同步状态 */
function onNativeClose() {
  if (open.value) {
    open.value = false
    emit('close')
  }
}

watch(
  open,
  async (v) => {
    await nextTick()
    const d = dialogEl.value
    if (!d) return
    if (v && !d.open) d.showModal()
    else if (!v && d.open) d.close()
  },
  { immediate: true },
)
</script>

<template>
  <dialog
    ref="dialogEl"
    class="modal"
    role="dialog"
    aria-modal="true"
    @click="onClick"
    @cancel="onCancel"
    @close="onNativeClose"
  >
    <div class="modal-box" v-bind="$attrs">
      <h3 v-if="title" class="font-bold text-lg text-base-content mb-4">{{ title }}</h3>
      <slot v-if="open" />
      <div v-if="open && $slots.actions" class="modal-action">
        <slot name="actions" />
      </div>
    </div>
  </dialog>
</template>
