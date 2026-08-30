export interface ConfirmOptions {
  /** 标题 */
  title?: string
  /** 消息内容 */
  message?: string
  /** 确认按钮文本 */
  confirmText?: string
  /** 取消按钮文本 */
  cancelText?: string
  /** 确认按钮样式类型 */
  confirmType?: 'primary' | 'error' | 'warning' | 'neutral'
  /** 是否显示取消按钮 */
  showCancel?: boolean
  /** 是否点击遮罩关闭 */
  closeOnClickOverlay?: boolean
  /** 是否按 ESC 关闭 */
  closeOnPressEscape?: boolean
}

export interface ConfirmResult {
  /** 用户是否确认 */
  confirmed: boolean
}
