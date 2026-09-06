/**
 * Plotly.js 懒加载器
 *
 * 从 dist/plotly-cartesian.min.js 动态加载 UMD 构建：
 * - 覆盖本项目所需 trace（scatter / bar / shapes）且比全量 plotly.min.js 小；
 * - 规避打包 plotly 源码（src/…）时其对 node `buffer` 的依赖。
 *
 * 类型策略：模块声明见 src/types/plotly-dist.d.ts（复用官方 lib 类型），
 * 此处将 API 收窄为项目实际使用面。
 */
export interface PlotlyApi {
  newPlot(root: HTMLElement, data: unknown[], layout?: unknown, config?: unknown): Promise<unknown>
  react(root: HTMLElement, data: unknown[], layout?: unknown, config?: unknown): Promise<unknown>
  purge(root: HTMLElement): void
  relayout(root: HTMLElement, layout: unknown): Promise<unknown>
}

let cached: Promise<PlotlyApi> | null = null

/**
 * 动态加载 plotly UMD 并缓存。
 * UMD 通过 module.exports 暴露自身；类型以官方 lib 为准（见 d.ts 声明）。
 */
export function loadPlotly(): Promise<PlotlyApi> {
  if (!cached) {
    cached = import('plotly.js/dist/plotly-cartesian.min.js').then((m) => {
      const api = (m.default ?? m) as {
        newPlot: PlotlyApi['newPlot']
        react: PlotlyApi['react']
        purge: PlotlyApi['purge']
        relayout: PlotlyApi['relayout']
      }
      return {
        newPlot: api.newPlot.bind(api),
        react: api.react.bind(api),
        purge: api.purge.bind(api),
        relayout: api.relayout.bind(api),
      }
    })
  }
  return cached
}
