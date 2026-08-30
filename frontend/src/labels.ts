/**
 * labels.ts - 全局文案常量
 *
 * 集中管理页面标题、Tab 名称、按钮文案等，避免不同页面各自翻译漂移。
 * 目前仅 zh-CN 一套；未来若需 i18n 可迁移至 vue-i18n/messages。
 */

/** 侧边栏 / 顶级页面标题 */
export const PAGE_TITLES = {
  insights: '分析洞察',
  settings: '项目概览',
  schedule: '进度管理',
  dailyReport: '日报处理',
} as const

/** insights 子页面标题（用于 Tab label 与 meta.title） */
export const INSIGHTS_TAB_LABELS = {
  optimization: '优化结果', // 原"多目标对比"，语义更清晰
  emission: '碳排放分析',
  comparison: '方案对比',
} as const

/** settings 子页面标题 */
export const SETTINGS_TAB_LABELS = {
  overview: '碳排放总览', // 原"概览"，与"项目概览"区分开
  info: '项目信息',
  resources: '资源管理',
  constraints: '资源限制',
  optimization: '优化配置',
  reuseConfigs: '材料复用',
} as const
