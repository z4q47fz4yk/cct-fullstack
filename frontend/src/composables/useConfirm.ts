import { h, ref, render, watch } from 'vue'
import ConfirmModal from '@/components/common/ConfirmModal.vue'
import type { ConfirmOptions, ConfirmResult } from '@/types/confirm'

interface ConfirmState extends ConfirmOptions {
  visible: boolean
  resolve: ((value: ConfirmResult) => void) | null
}

// 全局状态
const state = ref<ConfirmState>({
  visible: false,
  resolve: null,
  title: '确认',
  message: '',
  confirmText: '确认',
  cancelText: '取消',
  confirmType: 'primary',
  showCancel: true,
  closeOnClickOverlay: true,
  closeOnPressEscape: true,
})

// 挂载容器
let container: HTMLDivElement | null = null

// 是否已经初始化监听
let isWatching = false

/**
 * 渲染确认模态框
 */
function renderConfirmModal() {
  if (!container) {
    container = document.createElement('div')
    document.body.appendChild(container)
  }

  const vnode = h(ConfirmModal, {
    open: state.value.visible,
    'onUpdate:open': (val: boolean) => {
      state.value.visible = val
      // 当模态框关闭时，如果还没有 resolve，则 resolve 为取消
      if (!val && state.value.resolve) {
        state.value.resolve({ confirmed: false })
        state.value.resolve = null
      }
    },
    title: state.value.title,
    message: state.value.message,
    confirmText: state.value.confirmText,
    cancelText: state.value.cancelText,
    confirmType: state.value.confirmType,
    showCancel: state.value.showCancel,
    closeOnClickOverlay: state.value.closeOnClickOverlay,
    closeOnPressEscape: state.value.closeOnPressEscape,
    onConfirm: () => {
      if (state.value.resolve) {
        state.value.resolve({ confirmed: true })
        state.value.resolve = null
      }
      state.value.visible = false
    },
    onCancel: () => {
      if (state.value.resolve) {
        state.value.resolve({ confirmed: false })
        state.value.resolve = null
      }
      state.value.visible = false
    },
  })

  render(vnode, container)
}

/**
 * 初始化监听，当 visible 变化时自动重新渲染
 */
function initWatch() {
  if (isWatching) return
  isWatching = true

  watch(
    () => state.value.visible,
    () => {
      if (container) {
        renderConfirmModal()
      }
    },
  )
}

/**
 * 打开确认对话框
 */
export function confirm(options: ConfirmOptions): Promise<ConfirmResult> {
  return new Promise((resolve) => {
    // 初始化监听
    initWatch()

    // 更新状态
    state.value = {
      visible: true,
      resolve,
      title: options.title ?? '确认',
      message: options.message ?? '',
      confirmText: options.confirmText ?? '确认',
      cancelText: options.cancelText ?? '取消',
      confirmType: options.confirmType ?? 'primary',
      showCancel: options.showCancel ?? true,
      closeOnClickOverlay: options.closeOnClickOverlay ?? true,
      closeOnPressEscape: options.closeOnPressEscape ?? true,
    }

    // 渲染模态框
    renderConfirmModal()
  })
}

/**
 * 便捷方法：危险操作确认（删除等）
 */
export function confirmDanger(message: string, title: string = '确认删除'): Promise<ConfirmResult> {
  return confirm({
    title,
    message,
    confirmType: 'error',
    confirmText: '删除',
  })
}

/**
 * 便捷方法：警告确认（不可撤销但不像删除那样致命）
 * 例：停止长任务、重新开始、清空全部
 */
export function confirmWarn(message: string, title: string = '确认操作'): Promise<ConfirmResult> {
  return confirm({
    title,
    message,
    confirmType: 'warning',
    confirmText: '继续',
  })
}

/**
 * 便捷方法：信息确认
 */
export function confirmInfo(message: string, title: string = '提示'): Promise<ConfirmResult> {
  return confirm({
    title,
    message,
    confirmType: 'primary',
  })
}

/**
 * 组合式函数（用于组件内使用）
 */
export function useConfirm() {
  return {
    confirm,
    confirmDanger,
    confirmWarn,
    confirmInfo,
  }
}
