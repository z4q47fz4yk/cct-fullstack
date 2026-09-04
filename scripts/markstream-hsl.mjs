// 从 base.css 解析 oklch token，转 HSL 三元组，输出 markstream.css 主题桥接变量。
// 用法: node scripts/markstream-hsl.mjs  （生成 frontend/src/assets/markstream.css）
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const rawBase = readFileSync(join(root, 'frontend/src/assets/base.css'), 'utf8')
// 剔除 @theme inline {…}（里面是同名 var 引用，非真实 token）
const themeCss = rawBase.replace(/@theme\s+inline\s*{[^}]*}/g, '')

// ── oklch → sRGB → HSL ────────────────────────────────────────────────
const toLinear = (c) => {
  const c1 = c / 100
  return c1 <= 0.04045 ? c1 / 12.92 : ((c1 + 0.055) / 1.055) ** 2.4
}
const toSrgb = (c) => {
  const c1 = c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055
  return Math.max(0, Math.min(1, c1))
}
function oklchToRgb([l, c, h]) {
  // oklab
  const L = l
  const a = c * Math.cos((h * Math.PI) / 180)
  const b = c * Math.sin((h * Math.PI) / 180)
  // oklab → LMS
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.291485548 * b
  const l3 = l_ ** 3
  const m3 = m_ ** 3
  const s3 = s_ ** 3
  const r = toSrgb(+4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3)
  const g = toSrgb(-1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3)
  const bl = toSrgb(-0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3)
  return [r * 255, g * 255, bl * 255]
}
function rgbToHsl([r, g, b]) {
  r /= 255
  g /= 255
  b /= 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  let h = 0
  let s = 0
  const l = (max + min) / 2
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0)
        break
      case g:
        h = (b - r) / d + 2
        break
      default:
        h = (r - g) / d + 4
    }
    h *= 60
  }
  return [Math.round(h), Math.round(s * 100), Math.round(l * 100)]
}

const lightIdx = themeCss.lastIndexOf(`[data-theme='starglass-light'] {`)
const darkCss = themeCss.slice(0, lightIdx)
const lightCss = themeCss.slice(lightIdx)

function token(name, css) {
  const m = css.match(new RegExp(`--color-${name}:\\s*([^;]+);`))
  if (!m) throw new Error(`token not found: --color-${name}`)
  const v = m[1].trim()
  // oklch(l c h) 或 oklch(l c h / alpha)
  const om = v.match(/^oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*[\d.]+)?\)$/)
  if (!om) throw new Error(`not oklch: ${v}`)
  return [Number(om[1]), Number(om[2]), Number(om[3])]
}

// 需要保证解析到的是深色块的值（第一个匹配即 :root 深色块）
function hslTriple(name, css) {
  return rgbToHsl(oklchToRgb(token(name, css))).join(' ')
}

// 语义映射表（key: markstream 变量名 → base token 或固定值）
// scope: 从哪段 css 取 token
function makeMap(css) {
  return {
    '--markstream-ms-background': () => hslTriple('base-100', css),
    '--markstream-ms-foreground': () => hslTriple('base-content', css),
    '--markstream-ms-muted': () => hslTriple('base-200', css),
    '--markstream-ms-muted-foreground': () => hslTriple('fg-muted', css),
    '--markstream-ms-secondary': () => hslTriple('base-200', css),
    '--markstream-ms-secondary-foreground': () => hslTriple('base-content', css),
    '--markstream-ms-accent': () => hslTriple('base-300', css),
    '--markstream-ms-accent-foreground': () => hslTriple('base-content', css),
    '--markstream-ms-primary': () => hslTriple('primary', css),
    '--markstream-ms-primary-foreground': () => hslTriple('primary-content', css),
    '--markstream-ms-destructive': () => hslTriple('error', css),
    '--markstream-ms-destructive-foreground': () => hslTriple('error-content', css),
    '--markstream-ms-border': () => hslTriple('base-300', css),
    '--markstream-ms-ring': () => hslTriple('primary', css),
    '--markstream-ms-popover': () => hslTriple('base-100', css),
    '--markstream-ms-popover-foreground': () => hslTriple('base-content', css),
    '--markstream-ms-info': () => hslTriple('info', css),
    '--markstream-ms-info-foreground': () => hslTriple('info-content', css),
    '--markstream-ms-success': () => hslTriple('success', css),
    '--markstream-ms-success-foreground': () => hslTriple('success-content', css),
    '--markstream-ms-warning': () => hslTriple('warning', css),
    '--markstream-ms-warning-foreground': () => hslTriple('warning-content', css),
    '--markstream-ms-diff-added': () => hslTriple('success', css),
    '--markstream-ms-diff-removed': () => hslTriple('error', css),
    '--markstream-ms-highlight': () => '50 60% 72%',
    '--markstream-ms-highlight-foreground': () => '0 0% 0%',
  }
}

const DARK = makeMap(darkCss)
const LIGHT = makeMap(lightCss)

function block(section, themeName, map) {
  const lines = Object.keys(map).map((k) => `  ${k}: ${map[k]()};`)
  // 深色挂在 :root（首屏兜底）+ [data-theme='starglass']；亮色只挂对应选择器
  const sel = section === '深色' ? `:root,
[data-theme='${themeName}']` : `[data-theme='${themeName}']`
  return `/* ── ${section}：${themeName} ── */
${sel} {
${lines.join('\n')}
}`
}

const css = `/* ========== markstream.css（自动生成，勿手改） ==========
 * markstream-vue 流式 Markdown 渲染器主题桥接。
 *
 * 引入 markstream-vue/index.css 请走 main.ts 的 JS import（本文件不含 @import：
 * css @layer 内的 @import 会被构建器提升为运行时请求）。
 *
 * 自研工程面板主题（starglass / starglass-light，见 base.css）只定义 oklch
 * 色值，而 markstream-vue 需要 HSL 三元组变量（--ms-*）。此文件从 base.css
 * 语义 token 精确转换（oklch→sRGB→HSL），以「语义映射 + 主题定制」对齐
 * 两边，把 markstream 的浅色默认 palette 覆盖为工程主题。
 *
 * 重新生成：node scripts/markstream-hsl.mjs
 * ============================================================ */

/* 主题变量先于 .markstream-vue 覆盖规则定义（同层同优先级，后到者赢） */
${block('深色', 'starglass', DARK)}
${block('亮色', 'starglass-light', LIGHT)}

/* ── 应用到 markstream 容器（覆盖其默认值；两选择器优先级相同、后到者赢） ── */
:root .markstream-vue,
[data-theme='starglass'] .markstream-vue,
[data-theme='starglass-light'] .markstream-vue {
  --ms-background: var(--markstream-ms-background);
  --ms-foreground: var(--markstream-ms-foreground);
  --ms-muted: var(--markstream-ms-muted);
  --ms-muted-foreground: var(--markstream-ms-muted-foreground);
  --ms-secondary: var(--markstream-ms-secondary);
  --ms-secondary-foreground: var(--markstream-ms-secondary-foreground);
  --ms-accent: var(--markstream-ms-accent);
  --ms-accent-foreground: var(--markstream-ms-accent-foreground);
  --ms-primary: var(--markstream-ms-primary);
  --ms-primary-foreground: var(--markstream-ms-primary-foreground);
  --ms-destructive: var(--markstream-ms-destructive);
  --ms-destructive-foreground: var(--markstream-ms-destructive-foreground);
  --ms-border: var(--markstream-ms-border);
  --ms-ring: var(--markstream-ms-ring);
  --ms-popover: var(--markstream-ms-popover);
  --ms-popover-foreground: var(--markstream-ms-popover-foreground);
  --ms-info: var(--markstream-ms-info);
  --ms-info-foreground: var(--markstream-ms-info-foreground);
  --ms-success: var(--markstream-ms-success);
  --ms-success-foreground: var(--markstream-ms-success-foreground);
  --ms-warning: var(--markstream-ms-warning);
  --ms-warning-foreground: var(--markstream-ms-warning-foreground);
  --ms-diff-added: var(--markstream-ms-diff-added);
  --ms-diff-removed: var(--markstream-ms-diff-removed);
  --ms-highlight: var(--markstream-ms-highlight);
  --ms-highlight-foreground: var(--markstream-ms-highlight-foreground);
}

/* 代码块 / 行内结构使用更沉的工程底色（面板上叠代码时仍可读） */
:root .markstream-vue,
[data-theme='starglass'] .markstream-vue,
[data-theme='starglass-light'] .markstream-vue {
  --code-bg: var(--markstream-code-bg, var(--color-surface-deep));
  --code-header-bg: var(--markstream-code-header-bg, var(--color-base-200));
  --code-border: var(--markstream-code-border, var(--color-base-300));
  --code-fg: var(--markstream-code-fg, var(--color-base-content));
  --inline-code-bg: var(--markstream-inline-code-bg, var(--color-base-200));
  --inline-code-fg: var(--markstream-inline-code-fg, var(--color-base-content));
  --inline-code-border: var(--markstream-inline-code-border, var(--color-base-300));
  --link-color: var(--markstream-link-color, var(--color-info));
  --focus-ring: var(--markstream-focus-ring, var(--color-primary));
  --loading-spinner: var(--markstream-loading-spinner, var(--color-fg-muted));
  --loading-shimmer: var(--markstream-loading-shimmer, var(--color-base-200));
  --list-marker: var(--markstream-list-marker, var(--color-fg-muted));
  --list-counter-marker: var(--markstream-list-counter-marker, var(--color-fg-muted));
  --blockquote-border: var(--markstream-blockquote-border, var(--color-base-300));
  --blockquote-fg: var(--markstream-blockquote-fg, var(--color-fg-muted));
  --table-border: var(--markstream-table-border, var(--color-base-300));
  --table-header-bg: var(--markstream-table-header-bg, var(--color-base-200));
  --diagram-bg: var(--markstream-diagram-bg, var(--color-base-200));
  --diagram-border: var(--markstream-diagram-border, var(--color-base-300));
  --diagram-header-bg: var(--markstream-diagram-header-bg, var(--color-base-200));
  --modal-overlay: var(--markstream-modal-overlay, var(--color-panel-shadow));
  --modal-bg: var(--markstream-modal-bg, var(--color-panel));
  --modal-fg: var(--markstream-modal-fg, var(--color-base-content));
}
`

writeFileSync(join(root, 'frontend/src/assets/markstream.css'), css)
console.log('written frontend/src/assets/markstream.css')
