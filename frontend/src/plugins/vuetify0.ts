import { createTooltipPlugin } from '@vuetify/v0'
import type { App } from 'vue'

/**
 * Vuetify0 全局插件。
 *
 * 只注册 tooltip region 配置：
 * - `openDelay: 500` —— 悬停 0.5s 后才显示气泡（不用浏览器 `title` 的默认时机）；
 * - 其余保留默认（`closeDelay` 150ms、`skipDelay` 300ms 预热窗口：一个气泡刚关，
 *   悬停相邻条目时立即显示，无需再等一轮延迟）。
 *
 * 刻意不注册 `createThemePlugin` —— 主题由项目自身 `base.css` 变量 + `useTheme()`
 * 承担，再装一套主题系统会与 `[data-theme]` 体系冲突。
 *
 * @see https://0.vuetifyjs.com/composables/plugins/use-tooltip
 */
export default function vuetify0(app: App): void {
  app.use(createTooltipPlugin({ openDelay: 500 }))
}
