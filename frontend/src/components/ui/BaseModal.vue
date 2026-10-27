<script setup lang="ts">
/**
 * BaseModal - 统一模态框（原生 <dialog> 派）
 *
 * 行为（浏览器原生免费提供）：
 *   - 打开：showModal() → 背景 inert（无法交互）+ 首次焦点管理
 *   - Esc 关闭：原生 cancel 事件（closeOnEscape=false 时阻止）
 *   - 遮罩点击关闭：pointerdown 起点在遮罩上（target === dialog）即关闭
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

/**
 * 遮罩点击关闭：只在 pointerdown 起点的 target 就是 dialog 自身（即遮罩空白处）
 * 时才视为"点了遮罩"并关闭。这样「在 modal-box 内 pointerdown 开始选中文本，
 * 即使后续 mouseup 落在遮罩上」也不会误关。
 *
 * 为什么不直接监听 click：原生 click 事件在 mousedown 与 mouseup 跨元素时，
 * target 会退化为两者的共同祖先（这正是原 bug 的根因），所以无法可靠地判断
 * 用户到底点的是遮罩还是 modal-box 内部。pointerdown 起点判定跨鼠标/触屏/
 * 手写笔一致，且不受后续 mouseup 位置影响。
 *
 * 关于右键：pointerdown 对所有按键都会触发，因此需要排除非主按键 (右键、中键)，
 * 否则在遮罩上右键打开上下文菜单时会立即关闭弹窗。
 */
function onPointerDown(e: PointerEvent) {
  // 仅响应主按键：鼠标左键 / 触摸接触 / 手写笔接触。右键 button=2，中键 button=1。
  if (!closeOnOverlay || e.button !== 0) return
  const d = dialogEl.value
  if (d && e.target === d) closeModal()
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
    @pointerdown="onPointerDown"
    @cancel="onCancel"
    @close="onNativeClose"
  >
    <div class="modal-box" v-bind="$attrs">
      <!-- 头部：标题 + 关闭（设计稿 modal-head） -->
      <div v-if="title" class="flex items-center justify-between mb-4">
        <h3 class="font-semibold text-base text-base-content">{{ title }}</h3>
        <button
          type="button"
          class="btn-icon -mr-1"
          aria-label="关闭"
          @click="closeModal"
        >
          <span class="material-symbols-outlined icon-sm">close</span>
        </button>
      </div>
      <slot v-if="open" />
      <div v-if="open && $slots.actions" class="modal-action">
        <slot name="actions" />
      </div>
    </div>
  </dialog>
</template>
