/**
 * plotly.js dist UMD 的模块声明。
 *
 * 项目从 dist/plotly-cartesian.min.js 动态加载 UMD（避免打包其源码对
 * node `buffer` 的依赖）；运行时类型复用官方 lib/index.d.ts 的 default
 * 导出形态（newPlot/react/purge/relayout 等）。
 */
declare module 'plotly.js/dist/plotly-cartesian.min.js' {
  import type Plotly from 'plotly.js'
  const PlotlyDist: typeof Plotly
  export = PlotlyDist
}
