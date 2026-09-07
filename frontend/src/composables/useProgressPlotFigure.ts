/**
 * 施工进度 Plotly 主图的数据组装（纯函数）。
 *
 * 输入：领域数据（甘特行 / 碳排桶 / 天气点），输出：plotly figure 的
 * { data, layout }。组件层只负责挂载与生命周期，不接触业务语义。
 *
 * 布局（3 子区，同享日历 x 轴，纯手动 domain 不依赖 plotly grid）：
 *   1. 甘特区（上）：y = 工序分类轴，形状横道 + 每日进度折线
 *   2. 碳排柱区（中）：按粒度分桶，可堆叠
 *   3. 天气区（下）：气温 ℃（左轴）/ 降水 mm（右轴）双折线
 *
 * 颜色由页面经 props 注入（getThemeColors），避免模块级耦合主题状态。
 */
import { getThemeColors } from '@/utils/themeColors'
import type { PlotlyDataLayoutConfig, Data, Layout, Shape } from 'plotly.js'

/** 主题色（与 getThemeColors() 返回同构，避免依赖未导出的内部类型） */
export type ThemeColors = ReturnType<typeof getThemeColors>

/** 甘特行（已换算为真实日历日期字符串，YYYY-MM-DD） */
export interface TimelineTaskRow {
  taskId: number
  code: string
  name: string
  /** 计划开始（可为 null：无计划） */
  planStart: string | null
  /** 计划结束（可为 null） */
  planEnd: string | null
  /** 实际开始（可为 null：无进度） */
  actualStart: string | null
  /** 实际截止（完成日或今日；无进度为 null） */
  actualEnd: string | null
  /** 逐日累计进度 [(date, percent)] */
  series: [string, number][]
  currentPercent: number
  isCompleted: boolean
}

/** 碳排柱的单个数据点（按粒度一个桶） */
export interface CarbonBarDatum {
  /** 周期首日（plotly x 用真实日期，此处为 ISO 首日） */
  period: string
  /** 桶/维度的每段 (name, kg)；单段即总量 */
  segments: { name: string; value: number; color: string }[]
}

export interface WeatherDatum {
  /** 日期（日粒度，YYYY-MM-DD） */
  day: string
  temperatureC: number | null
  precipitationMm: number | null
}

export type PlotGranularity = 'day' | 'week' | 'month'

export interface ProgressPlotData {
  tasks: TimelineTaskRow[]
  carbon: CarbonBarDatum[]
  weather: WeatherDatum[]
  granularity: PlotGranularity
  /** 日历 x 轴最小/最大日期（YYYY-MM-DD），自动从数据推导 */
  minDate: string
  maxDate: string
  /** 主题色（页面注入 getThemeColors()） */
  colors: ThemeColors
  /** 「今天」ISO（当前日期竖线） */
  todayIso: string
}

const MS = 86_400_000

/** 'YYYY-MM-DD' → epoch ms（本地时区，避免 UTC 偏移） */
function toMs(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y!, m! - 1, d!).getTime()
}

/**
 * 组装 figure。
 */
export function buildProgressPlotFigure(d: ProgressPlotData): PlotlyDataLayoutConfig {
  const { tasks, carbon, weather, granularity, minDate, maxDate, colors, todayIso } = d
  const data: Data[] = []
  const shapes: Shape[] = []
  const n = tasks.length

  const PLAN_H = 0.8
  const ACT_H = 0.4

  // 甘特分类轴：任务行在 y 轴的位置（上方为第 0 行 → 大 y）
  const taskY = (i: number) => n - 1 - i

  // x 范围（ms）
  const x0 = toMs(minDate)
  const x1 = toMs(maxDate)
  const xRange: [number, number] = [x0, x1]

  // 自动刻度间隔：日=1d 显示太密 → 7d；周=月首；月=月首（tickformat 控制）
  const isDay = granularity === 'day'
  const dtick = isDay ? 7 * MS : 30 * MS
  const tickformat = isDay ? '%m-%d' : granularity === 'week' ? '%m-%d' : '%Y-%m'

  // ──── 甘特区（上 ~55%） ──────────────────────────────────
  // 计划横道（灰半透明）
  for (const t of tasks) {
    if (!t.planStart || !t.planEnd) continue
    const i = tasks.indexOf(t)
    const y = taskY(i)
    shapes.push({
      type: 'rect',
      xref: 'x' as '/^x([2-9]|[1-9][0-9]+)?( domain)?$/',
      yref: 'y' as '/^y([2-9]|[1-9][0-9]+)?( domain)?$/',
      x0: toMs(t.planStart),
      x1: toMs(t.planEnd),
      y0: y - PLAN_H / 2,
      y1: y + PLAN_H / 2,
      fillcolor: colors.label,
      opacity: 0.35,
      line: { width: 0 },
      layer: 'between',
    })
  }
  // 实际横道（按完成态着色）
  for (const t of tasks) {
    if (!t.actualStart || !t.actualEnd) continue
    const i = tasks.indexOf(t)
    const y = taskY(i)
    const c = t.isCompleted ? colors.success : colors.info
    shapes.push({
      type: 'rect',
      xref: 'x' as '/^x([2-9]|[1-9][0-9]+)?( domain)?$/',
      yref: 'y' as '/^y([2-9]|[1-9][0-9]+)?( domain)?$/',
      x0: toMs(t.actualStart),
      x1: toMs(t.actualEnd),
      y0: y - ACT_H / 2,
      y1: y + ACT_H / 2,
      fillcolor: c,
      opacity: 0.85,
      line: { width: 0 },
      layer: 'between',
    })
  }

  // 计划匀速进度线（跨整条计划的淡虚线）
  for (const t of tasks) {
    if (!t.planStart || !t.planEnd) continue
    const i = tasks.indexOf(t)
    data.push({
      type: 'scatter',
      x: [toMs(t.planStart), toMs(t.planEnd)],
      y: [taskY(i) + PLAN_H / 2, taskY(i) - PLAN_H / 2],
      mode: 'lines',
      line: { color: colors.label, width: 1, dash: 'dot' },
      hoverinfo: 'skip',
      showlegend: false,
      xaxis: 'x',
      yaxis: 'y',
    })
  }

  // 实际每日累计进度折线（映射到实际条高度区间内）
  for (const t of tasks) {
    if (!t.actualStart || t.series.length === 0) continue
    const i = tasks.indexOf(t)
    const y = taskY(i)
    const x: number[] = []
    const yy: number[] = []
    const pcts: number[] = []
    x.push(toMs(t.actualStart))
    yy.push(y - ACT_H / 2)
    pcts.push(0)
    for (const [dateStr, pct] of t.series) {
      x.push(toMs(dateStr))
      yy.push(y - ACT_H / 2 + (pct / 100) * ACT_H)
      pcts.push(pct)
    }
    data.push({
      type: 'scatter',
      x,
      y: yy,
      mode: 'lines+markers',
      line: { color: colors.accel, width: 2 },
      marker: { size: 5, color: colors.accel },
      customdata: pcts,
      showlegend: i === 0,
      legendgroup: 'progress',
      name: i === 0 ? '每日进度' : '',
      hovertemplate: `${t.name}<br>%{x|%m-%d} 进度 %{customdata}%<extra></extra>`,
      xaxis: 'x',
      yaxis: 'y',
    })
  }

  // 当前日期竖线
  if (todayIso) {
    shapes.push({
      type: 'line',
      xref: 'x' as '/^x([2-9]|[1-9][0-9]+)?( domain)?$/',
      yref: 'paper',
      x0: toMs(todayIso),
      x1: toMs(todayIso),
      y0: 0,
      y1: 1,
      line: { color: colors.error, width: 2, dash: 'dot' },
      layer: 'above',
    })
  }

  // 占位 scatter：驱动 y 分类轴显示全部行（含无任何日期的空任务）
  data.push({
    type: 'scatter',
    x: tasks.map(() => x0),
    y: tasks.map((_, i) => taskY(i)),
    mode: 'markers',
    marker: { size: 1, opacity: 0 },
    hoverinfo: 'skip',
    showlegend: false,
    xaxis: 'x',
    yaxis: 'y',
  })

  // ──── 碳排柱区（中） ─────────────────────────────────────
  if (carbon.length > 0) {
    // 所有段名（保持首桶顺序）
    const catNames = Array.from(new Set(carbon.flatMap((b) => b.segments.map((s) => s.name))))
    for (const catName of catNames) {
      const color =
        carbon.flatMap((b) => b.segments).find((s) => s.name === catName)?.color ?? colors.info
      const vals = carbon.map((b) => {
        const seg = b.segments.find((s) => s.name === catName)
        return seg?.value ?? 0
      })
      data.push({
        type: 'bar',
        x: carbon.map((b) => toMs(b.period)),
        y: vals,
        name: catName,
        customdata: vals,
        hovertemplate: `${catName} %{customdata}<extra></extra>`,
        marker: { color },
        xaxis: 'x2',
        yaxis: 'y2',
      })
    }
  }

  // ──── 天气区（下） ───────────────────────────────────────
  if (weather.length > 0) {
    const wx = weather.map((w) => toMs(w.day))
    data.push({
      type: 'scatter',
      x: wx,
      y: weather.map((w) => w.temperatureC),
      name: '气温',
      mode: 'lines+markers',
      line: { color: colors.accel, width: 2 },
      marker: { size: 5 },
      connectgaps: false,
      hovertemplate: '%{x|%Y-%m-%d} 气温 %{y}℃<extra></extra>',
      xaxis: 'x3',
      yaxis: 'y3',
    })
    data.push({
      type: 'scatter',
      x: wx,
      y: weather.map((w) => w.precipitationMm),
      name: '降水',
      mode: 'lines+markers',
      line: { color: colors.info, width: 2 },
      marker: { size: 5 },
      connectgaps: false,
      hovertemplate: '%{x|%Y-%m-%d} 降水 %{y}mm<extra></extra>',
      xaxis: 'x3',
      yaxis: 'y4',
    })
  }

  // ──── layout（手动 domain，三区上下排布） ─────────────────
  const layout: Layout = {
    // 甘特区
    xaxis: {
      type: 'date',
      range: xRange,
      domain: [0, 1],
      anchor: 'y' as '/^y([2-9]|[1-9][0-9]+)?( domain)?$/', // plotly.js 内部类型错误
      matches: 'x2' as '/^x([2-9]|[1-9][0-9]+)?( domain)?$/',
      dtick,
      tickformat,
      tickangle: isDay ? -30 : 0,
      showticklabels: false, // 隐藏刻度标签
      showgrid: true,
      gridcolor: colors.splitLine,
    },
    yaxis: {
      autorange: true,
      range: [-0.8, n - 0.2],
      domain: [0.42, 1],
      anchor: 'x' as '/^x([2-9]|[1-9][0-9]+)?( domain)?$/',
      showgrid: true,
      gridcolor: colors.splitLine,
      tickmode: 'array',
      tickvals: tasks.map((_, i) => taskY(i)),
      ticktext: tasks.map((t) => `${t.code} ${t.name}`),
    },
    // 碳排区
    xaxis2: {
      type: 'date',
      range: xRange,
      domain: [0, 1],
      anchor: 'y2' as '/^y([2-9]|[1-9][0-9]+)?( domain)?$/',
      dtick,
      tickformat,
      tickangle: isDay ? -30 : 0,
      showgrid: true,
      gridcolor: colors.splitLine,
    },
    yaxis2: {
      title: { text: '碳排 (kg)' },
      domain: [0.22, 0.38],
      anchor: 'x2' as '/^x([2-9]|[1-9][0-9]+)?( domain)?$/',
      showgrid: true,
      gridcolor: colors.splitLine,
      zeroline: false,
    },
    // 天气区
    xaxis3: {
      type: 'date',
      range: xRange,
      domain: [0, 1],
      anchor: 'y3' as '/^y([2-9]|[1-9][0-9]+)?( domain)?$/',
      dtick,
      tickformat,
      tickangle: isDay ? -30 : 0,
      showgrid: true,
      gridcolor: colors.splitLine,
    },
    yaxis3: {
      title: { text: '气温 ℃' },
      domain: [0, 0.18],
      anchor: 'x3' as '/^x([2-9]|[1-9][0-9]+)?( domain)?$/',
      showgrid: false,
      zeroline: false,
    },
    yaxis4: {
      title: { text: '降水 mm' },
      domain: [0, 0.18],
      anchor: 'free',
      position: 0,
      overlaying: 'y3' as '/^y([2-9]|[1-9][0-9]+)?( domain)?$/',
      side: 'right',
      showgrid: false,
      zeroline: false,
    },
    shapes,
    margin: { l: 150, r: 70, t: 30, b: 40 },
    legend: { orientation: 'h', y: 1.02, x: 0, xanchor: 'left', yanchor: 'bottom' },
    hovermode: 'closest',
    font: { size: 11 },
    // @ts-expect-error -- plotly.js 4.0.0 类型暂时缺失 barmode
    barmode: 'stack',
    bargap: 0.25,
  }

  return { data, layout }
}
