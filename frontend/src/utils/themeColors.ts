/**
 * themeColors - 从 CSS 变量读取图表所需的颜色
 *
 * 替代图表内硬编码的 hex 颜色，让主题切换时自动跟随。
 * 缓存于模块级懒初始化的 ref，避免每次读取触发 reflow。
 */
type ThemeColorKey =
  | 'axis'
  | 'splitLine'
  | 'label'
  | 'baseContent'
  | 'primary'
  | 'error'
  | 'success'
  | 'warning'
  | 'info'
  | 'accel'
  | 'cyan'
  | 'indigo'
  | 'blue'
  | 'violet'
  | 'purple'
  | 'teal'
  | 'green'
  | 'amber'
  | 'orange'
  | 'rose'
  | 'red'
  | 'emerald'
  | 'surfaceDeep'

type ThemeColors = Record<ThemeColorKey, string>

import { shallowRef } from 'vue'

let cached: ThemeColors | null = null
const themeVersion = shallowRef(0)

function readCssVars(): ThemeColors {
  const fallback = (v: string) => v
  if (typeof window === 'undefined') {
    return {} as ThemeColors
  }
  const styles = getComputedStyle(document.documentElement)
  const get = (key: string, fb: string): string => {
    const v = styles.getPropertyValue(key).trim()
    return v.length > 0 ? v : fb
  }
  return {
    axis: fallback(get('--color-neutral', '#374151')),
    splitLine: fallback(get('--color-base-300', '#1f2937')),
    label: fallback(get('--color-fg-muted', '#a1a1aa')),
    baseContent: fallback(get('--color-base-content', '#f6f8f7')),
    primary: fallback(get('--color-primary', '#1fdb6d')),
    error: fallback(get('--color-error', '#ef4444')),
    success: fallback(get('--color-success', '#1fdb6d')),
    warning: fallback(get('--color-warning', '#f59e0b')),
    info: fallback(get('--color-info', '#3b82f6')),
    accel: fallback(get('--color-accel', '#fb923c')),

    // ── 分析洞察专用语义色（设计师 another-color.html 配色） ──
    cyan: fallback(get('--color-cyan', '#22d3ee')),
    indigo: fallback(get('--color-indigo', '#818cf8')),
    blue: fallback(get('--color-blue', '#60a5fa')),
    violet: fallback(get('--color-violet', '#a78bfa')),
    purple: fallback(get('--color-purple', '#c084fc')),
    teal: fallback(get('--color-teal', '#2dd4bf')),
    green: fallback(get('--color-green', '#4ade80')),
    amber: fallback(get('--color-amber', '#fbbf24')),
    orange: fallback(get('--color-orange', '#fb923c')),
    rose: fallback(get('--color-rose', '#fb7185')),
    red: fallback(get('--color-red', '#f87171')),
    emerald: fallback(get('--color-emerald', '#34d399')),

    // ── 面板与边框 ──
    surfaceDeep: fallback(get('--color-surface-deep', '#0d1117')),
  }
}

export function getThemeColors(): ThemeColors {
  // 读取 themeVersion 以建立响应式依赖（shallowRef）
  const _ = themeVersion.value
  if (!cached) cached = readCssVars()
  return cached
}

/** 当主题切换（如 dark/light）时调用，重新读取 */
export function refreshThemeColors() {
  cached = readCssVars()
  themeVersion.value++
}

/**
 * 图表切片调色板（按 sortOrder 顺序稳定取色）。
 * 与标签/图表设计稿的切片配色一致，主题切换自动跟随。
 * 工程面板约定：避免相邻同色相（原 teal/green/emerald 三连绿已拆散）。
 */
export function getSlicePalette(): string[] {
  const tc = getThemeColors()
  return [
    tc.blue,
    tc.indigo,
    tc.violet,
    tc.purple,
    tc.cyan,
    tc.teal,
    tc.green,
    tc.amber,
    tc.orange,
    tc.rose,
    tc.red,
    tc.emerald,
  ]
}

/** 按索引取切片颜色（超出调色板长度时循环使用） */
export function getSliceColor(index: number): string {
  const palette = getSlicePalette()
  return palette[index % palette.length] ?? palette[0]!
}

/**
 * 将 #rrggbb / #rgb 转为 "r, g, b" 字符串。
 * 用于 ECharts rgba 拼接：rgba(${hexToRgb(hex)}, 0.4)
 * 非 hex 输入原样返回。
 */
export function hexToRgb(color: string | undefined): string {
  if (!color) return '255, 255, 255'
  const hex = color.trim().replace('#', '')
  if (hex.length === 3) {
    const r = parseInt(hex[0]! + hex[0]!, 16)
    const g = parseInt(hex[1]! + hex[1]!, 16)
    const b = parseInt(hex[2]! + hex[2]!, 16)
    return `${r}, ${g}, ${b}`
  }
  if (hex.length === 6) {
    const r = parseInt(hex.slice(0, 2), 16)
    const g = parseInt(hex.slice(2, 4), 16)
    const b = parseInt(hex.slice(4, 6), 16)
    return `${r}, ${g}, ${b}`
  }
  return color
}

/**
 * 给颜色叠加 alpha。已带 rgba 的颜色直接拼接 alpha；hex 颜色转为 rgba。
 */
export function withOpacity(color: string | undefined, alpha: number): string {
  if (!color) return `rgba(255, 255, 255, ${alpha})`
  const trimmed = color.trim()
  if (trimmed.startsWith('rgba')) {
    // 把末尾 ")" 前的 ",x)" 替换为 ",alpha)"
    return trimmed.replace(/,\s*[\d.]+\s*\)$/, `, ${alpha})`)
  }
  if (trimmed.startsWith('rgb')) {
    return trimmed.replace('rgb', 'rgba').replace(')', `, ${alpha})`)
  }
  if (trimmed.startsWith('#')) {
    return `rgba(${hexToRgb(trimmed)}, ${alpha})`
  }
  return trimmed
}

/**
 * 资源类别主题色（随主题切换）。
 * 类别色与语义色分离：蓝=人工、琥珀=机械、青=材料、紫=运输、灰=其他。
 * 注意：材料类别不用绿（绿保留给"低碳"语义）。
 */
export function getCategoryColor(
  category: 'labor' | 'machinery' | 'material' | 'transport' | 'others',
): string {
  const tc = getThemeColors()
  switch (category) {
    case 'labor':
      return tc.blue
    case 'machinery':
      return tc.amber
    case 'material':
      return tc.cyan
    case 'transport':
      return tc.purple
    default:
      return tc.label
  }
}
