/**
 * 通用 SearchableSelect 类型定义
 *
 * - T: 选项原始对象的类型（例如 ResourceResp）
 * - V: v-model 值的类型（例如 number = resource.id）
 *
 * 约定：父组件负责把远端数据准备成 SelectOption<T, V>[]；
 * SearchableSelect 本身不调用 API，仅做客户端过滤与选择。
 */

export interface SelectOption<T, V = number> {
  /** 原始对象，change 事件透传给父级 */
  raw: T
  /** v-model 实际写入的值 */
  value: V
  /** 主显示文本 */
  label: string
  /** 副显示文本（灰色二级行），可选 */
  description?: string
  /** 禁用该选项（仍显示但不可选） */
  disabled?: boolean
}
