<script setup lang="ts">
/**
 * 碳排数据看板 - 全屏深色大屏（设计稿 · 施工碳排放多目标优化数据看板）
 *
 * 三栏：左 340（累计碳排放 · 碳排放构成 · 方案推荐）
 *      中自适应（六指标长条 · 项目综合展示，跨第一二行通栏）
 *      右 380（项目信息 · 用能碳排趋势 · 用能分布）
 * 底行：方案推荐 · 物化碳排趋势 · 用能分布 三卡同高、顶部对齐
 *
 * 数据：useCarbonStats（周期条目含阶段/水电桶）、usePlanApi（基线横道）、
 *      useOptimizeRecords（最新成功运行的 Pareto 解集）、projectExtras（项目图片）。
 * 进入本页临时切深色主题，离开恢复；图表经 getThemeColors() 取色。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useQuery } from '@pinia/colada'
import { useCarbonStats } from '@/composables/useCarbonStats'
import { usePlanApi } from '@/composables/usePlanApi'
import { useProjectApi } from '@/composables/useProjectApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useWeatherApi } from '@/composables/useWeatherApi'
import { loadProjectExtras } from '@/utils/projectExtras'
import { getThemeColors, withOpacity, getCategoryColor, refreshThemeColors } from '@/utils/themeColors'
import { fmtNumber } from '@/utils/format'
import {
  listOptimizeRecordsQuery,
  listOptimizeRecordResultQuery,
} from '@/client/@pinia/colada.gen'
import type { ResourceCategory } from '@/client/types.gen'
import SegmentControl from '@/components/common/SegmentControl.vue'

use([BarChart, LineChart, PieChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

definePage({
  meta: {
    title: '碳排数据看板',
    showInNav: false,
    parentName: '/project/[projectId]/statistics',
    navOrder: 1,
    fullscreen: true,
  },
})

// ─── 临时深色主题 ─────────────────────────────────────────
const previousTheme = ref<string | null>(null)
onMounted(() => {
  previousTheme.value = document.documentElement.dataset.theme ?? null
  document.documentElement.dataset.theme = 'starglass'
  refreshThemeColors()
})
onBeforeUnmount(() => {
  if (previousTheme.value) document.documentElement.dataset.theme = previousTheme.value
  else delete document.documentElement.dataset.theme
  refreshThemeColors()
})

// ─── 时钟 ────────────────────────────────────────────────
const now = ref(new Date())
let clockTimer: number | undefined
onMounted(() => {
  clockTimer = window.setInterval(() => (now.value = new Date()), 1000)
})
onBeforeUnmount(() => {
  if (clockTimer !== undefined) window.clearInterval(clockTimer)
})
const dateText = computed(() =>
  now.value.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }),
)

// ─── 数据 ────────────────────────────────────────────────
const { totalEmissionTon, byMonth, byCategory, byBucket, byResource, periodItems } =
  useCarbonStats()
const dayStats = useCarbonStats(() => 'day')
const { plan, isPlanMissing } = usePlanApi()
const { project, projects } = useProjectApi()
const { currentProjectId } = useProjectContext()
const { weather } = useWeatherApi()
const router = useRouter()

/** 当前天气：晴 / 降水 + 温度（无数据显 —） */
const weatherToday = computed(() => {
  const today = now.value.toISOString().slice(0, 10)
  const list = weather.value ?? []
  return list.find((w) => w.date === today) ?? list[list.length - 1] ?? null
})
const weatherText = computed(() => {
  const w = weatherToday.value
  if (!w) return '—'
  const rainy = (w.precipitationMm ?? 0) >= 0.1
  const temp = w.temperatureC === null || w.temperatureC === undefined ? '' : ` ${w.temperatureC}℃`
  return `${rainy ? '降水' : '晴'}${temp}`
})
/** 时间点（HH:MM） */
const timePoint = computed(() =>
  now.value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }),
)

const projectOptions = computed(() =>
  (projects.value ?? []).map((p) => ({ value: String(p.id), label: p.name })),
)
const currentProjectIdStr = computed(() =>
  project.value?.id != null ? String(project.value.id) : '',
)
function switchProject(id: string) {
  if (id && id !== currentProjectIdStr.value) router.push(`/project/${id}/statistics`)
}
function goBack() {
  const id = project.value?.id
  router.push(id != null ? `/project/${id}/settings/info` : '/')
}

const projectImage = ref('')
function refreshProjectImage() {
  projectImage.value = loadProjectExtras(project.value?.id).image_data ?? ''
}
watch(() => project.value?.id, refreshProjectImage, { immediate: true })

// ─── 阶段槽位（固定顺序：建材生产 / 建材运输 / 建筑建造） ──
type StageSlot = 'production' | 'transport' | 'construction'
const STAGE_ORDER: Array<{ slot: StageSlot; label: string }> = [
  { slot: 'production', label: '建材生产' },
  { slot: 'transport', label: '建材运输' },
  { slot: 'construction', label: '建筑建造' },
]

/** 桶名 → 阶段槽位（水电等桶返回 null，不计入三阶段） */
function stageSlotOf(bucket: string | null | undefined): StageSlot | null {
  const b = bucket ?? ''
  if (b.includes('生产')) return 'production'
  if (b.includes('运输')) return 'transport'
  if (b.includes('建造') || b.includes('施工')) return 'construction'
  return null
}

// ─── 六指标长条 ──────────────────────────────────────────
const buildingArea = computed(() => project.value?.building_area ?? null)
const intensityKg = computed(() => {
  const area = buildingArea.value
  if (!area || area <= 0) return null
  return Math.round((totalEmissionTon.value * 1000) / area)
})
const kpis = computed(() => [
  { label: '建筑面积', value: buildingArea.value === null ? '—' : fmtNumber(buildingArea.value, 0), unit: 'm²', icon: 'domain' },
  { label: '累计碳排放', value: fmtNumber(totalEmissionTon.value, 1), unit: 'tCO₂e', icon: 'eco' },
  { label: '碳排强度', value: intensityKg.value === null ? '—' : fmtNumber(intensityKg.value, 0), unit: 'kgCO₂e/m²', icon: 'speed' },
  { label: '优化工期', value: plan.value ? fmtNumber(plan.value.totalDuration, 0) : '—', unit: plan.value ? '天' : '', icon: 'schedule' },
  { label: '优化成本', value: plan.value ? fmtNumber(plan.value.totalCost / 10000, 0) : '—', unit: plan.value ? '万元' : '', icon: 'payments' },
  { label: '边际减排成本', value: '—', unit: '元/t', icon: 'trending_down' },
])

// ─── 累计碳排放（固定阶段顺序 + 超标/不超标） ──────────────
const emissionLimit = computed(() => project.value?.construction_carbon_emission_limit ?? null)
const overLimit = computed(
  () => emissionLimit.value !== null && totalEmissionTon.value > emissionLimit.value,
)

const stageRows = computed(() => {
  const total = totalEmissionTon.value
  const sums: Record<StageSlot, number> = { production: 0, transport: 0, construction: 0 }
  for (const b of byBucket.value) {
    const slot = stageSlotOf(b.bucket)
    if (slot) sums[slot] += b.emissionKg / 1000
  }
  return STAGE_ORDER.map(({ slot, label }) => ({
    name: label,
    valueT: sums[slot],
    pct: total > 0 ? Math.round((sums[slot] / total) * 100) : 0,
  }))
})

// ─── 碳排放构成：阶段 / 分部分项工程 切换 ─────────────────
const compositionMode = ref<'stage' | 'wbs'>('stage')
const COMPOSITION_OPTIONS = [
  { value: 'stage', label: '阶段' },
  { value: 'wbs', label: '分部分项工程' },
] as const

const compositionData = computed(() => {
  if (compositionMode.value === 'stage') {
    return byBucket.value.map((b) => ({ name: b.bucket, kg: b.emissionKg }))
  }
  // 分部分项工程：按资源（分项）聚合，Top8 + 其他
  const sorted = [...byResource.value].sort((a, b) => b.emissionKg - a.emissionKg)
  const top = sorted.slice(0, 8).map((r) => ({ name: r.resourceName, kg: r.emissionKg }))
  const restKg = sorted.slice(8).reduce((s, r) => s + r.emissionKg, 0)
  if (restKg > 0) top.push({ name: '其他', kg: restKg })
  return top
})

const compositionOption = computed(() => {
  const C = getThemeColors()
  const items = compositionData.value.filter((i) => i.kg > 0)
  if (items.length === 0) return {}
  const palette = [C.cyan, C.blue, C.emerald, C.amber, C.violet, C.purple, C.teal, C.orange, C.rose]
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.primary, 0.3),
      textStyle: { color: C.baseContent },
      formatter: (p: { name: string; value: number; percent: number }) =>
        `${p.name}<br/>${fmtNumber(p.value / 1000, 2)} t · ${p.percent}%`,
    },
    legend: {
      orient: 'vertical',
      right: 4,
      top: 'middle',
      textStyle: { color: withOpacity(C.baseContent, 0.65), fontSize: legendFontSize.value },
    },
    series: [
      {
        type: 'pie' as const,
        radius: ['46%', '70%'],
        center: ['36%', '50%'],
        avoidLabelOverlap: true,
        label: { show: false },
        data: items.map((i, idx) => ({
          name: i.name,
          value: Math.round(i.kg),
          itemStyle: { color: palette[idx % palette.length] },
        })),
      },
    ],
  }
})

// ─── 方案推荐（最新成功运行的 Pareto 解集） ───────────────
const runsQuery = useQuery(() => ({
  ...listOptimizeRecordsQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: 50 },
  }),
  enabled: currentProjectId.value !== null,
}))

const latestSuccessRunId = computed(() => {
  const runs = runsQuery.state.value?.data?.items ?? []
  const ok = runs.filter((r) => r.status === 'SUCCESS')
  ok.sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''))
  return ok[0]?.id ?? null
})

const solutionsQuery = useQuery(() => ({
  ...listOptimizeRecordResultQuery({
    path: { project_id: currentProjectId.value!, id: latestSuccessRunId.value! },
    query: { per_page: 100 },
  }),
  enabled: currentProjectId.value !== null && latestSuccessRunId.value !== null,
}))

const solutions = computed(() => solutionsQuery.state.value?.data?.items ?? [])

/** 方案行：P-编号 / 工期 / 成本 / 碳排 / 结论（最少碳排 = 推荐） */
const schemeRows = computed(() => {
  if (solutions.value.length > 0) {
    const minEmission = Math.min(...solutions.value.map((s) => s.emission))
    return solutions.value.slice(0, 4).map((s) => ({
      id: s.id,
      name: `P-${s.id}`,
      duration: s.duration,
      costWan: s.cost / 10000,
      emissionT: s.emission / 1000,
      recommended: s.emission === minEmission,
    }))
  }
  if (plan.value) {
    return [
      {
        id: plan.value.id,
        name: '当前基线',
        duration: plan.value.totalDuration,
        costWan: plan.value.totalCost / 10000,
        emissionT: plan.value.totalEmission / 1000,
        recommended: true,
      },
    ]
  }
  return []
})

// ─── 项目综合展示（固定高度；图表 = 横道图 / 散点图 / 方案对比） ──
const showcaseMode = ref<'image' | 'chart'>('image')
const SHOWCASE_OPTIONS = [
  { value: 'chart', label: '图表' },
  { value: 'image', label: '项目图片' },
] as const
const chartMode = ref<'gantt' | 'scatter' | 'compare'>('gantt')
const CHART_OPTIONS = [
  { value: 'gantt', label: '横道图' },
  { value: 'scatter', label: '散点图' },
  { value: 'compare', label: '方案对比' },
] as const

const dashBase = computed(() => getThemeColors())

// ─── 图例字号自适应屏幕（以 1920px 宽为基准 12px，限幅 10–16） ──
const legendFontSize = ref(12)
function updateLegendFontSize() {
  legendFontSize.value = Math.min(16, Math.max(10, Math.round(window.innerWidth / 160)))
}
onMounted(updateLegendFontSize)
window.addEventListener('resize', updateLegendFontSize)
onBeforeUnmount(() => window.removeEventListener('resize', updateLegendFontSize))

/** 横道图：基线方案分工序横道（offset 透明 + 工期条） */
const ganttOption = computed(() => {
  const C = dashBase.value
  const tasks = [...(plan.value?.tasks ?? [])].sort((a, b) => a.start - b.start)
  if (tasks.length === 0) return {}
  const minStart = Math.min(...tasks.map((t) => t.start))
  const maxEnd = Math.max(...tasks.map((t) => t.start + t.duration))
  return {
    backgroundColor: 'transparent',
    grid: { left: 110, right: 20, top: 8, bottom: 24 },
    tooltip: {
      trigger: 'item',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.primary, 0.3),
      textStyle: { color: C.baseContent },
      formatter: (p: { seriesIndex: number; dataIndex: number }) => {
        if (p.seriesIndex !== 1) return ''
        const t = tasks[p.dataIndex]
        if (!t) return ''
        return `<b>${t.code} ${t.name}</b><br/>开始：第 ${t.start - minStart} 天<br/>工期：${t.duration} 天`
      },
    },
    xAxis: {
      type: 'value' as const,
      min: 0,
      max: Math.max(maxEnd - minStart, 1),
      interval: Math.ceil((maxEnd - minStart) / 6),
      axisLabel: {
        color: withOpacity(C.baseContent, 0.6),
        formatter: (v: number) => `第${v}天`,
      },
      splitLine: { lineStyle: { color: withOpacity(C.label, 0.1) } },
    },
    yAxis: {
      type: 'category' as const,
      inverse: true,
      data: tasks.map((t) => `${t.code} ${t.name}`.slice(0, 12)),
      axisLabel: { color: withOpacity(C.baseContent, 0.65), fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar' as const,
        stack: 'gantt',
        silent: true,
        barWidth: 10,
        itemStyle: { color: 'transparent' },
        data: tasks.map((t) => t.start - minStart),
      },
      {
        type: 'bar' as const,
        stack: 'gantt',
        barWidth: 10,
        itemStyle: { borderRadius: 3, color: C.cyan },
        data: tasks.map((t) => t.duration),
      },
    ],
  }
})

/** 散点图：x=工期，y=碳排，气泡标注成本；最少碳排高亮 */
const scatterOption = computed(() => {
  const C = dashBase.value
  const items = solutions.value
  if (items.length === 0) return {}
  const minEmission = Math.min(...items.map((s) => s.emission))
  return {
    backgroundColor: 'transparent',
    grid: { left: 52, right: 24, top: 30, bottom: 30 },
    tooltip: {
      trigger: 'item',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.primary, 0.3),
      textStyle: { color: C.baseContent },
      formatter: (p: { data: [number, number, number, number] }) => {
        const [duration, emissionT, costWan, id] = p.data
        return `<b>P-${id}</b><br/>工期：${duration} 天<br/>碳排：${fmtNumber(emissionT, 1)} t<br/>成本：${fmtNumber(costWan, 0)} 万元`
      },
    },
    xAxis: {
      type: 'value' as const,
      name: '工期（天）',
      nameTextStyle: { color: withOpacity(C.baseContent, 0.5) },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
      splitLine: { lineStyle: { color: withOpacity(C.label, 0.1) } },
    },
    yAxis: {
      type: 'value' as const,
      name: '碳排放（tCO₂e）',
      nameTextStyle: { color: withOpacity(C.baseContent, 0.5) },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
      splitLine: { lineStyle: { color: withOpacity(C.label, 0.1) } },
    },
    series: [
      {
        type: 'scatter' as const,
        symbolSize: 14,
        itemStyle: {
          color: (p: { data: [number, number, number, number] }) =>
            p.data[1] * 1000 === minEmission ? C.cyan : withOpacity(C.blue, 0.85),
          borderColor: C.cyan,
          borderWidth: 1,
        },
        label: {
          show: true,
          position: 'top',
          fontSize: 10,
          color: withOpacity(C.baseContent, 0.75),
          formatter: (p: { data: [number, number, number, number] }) =>
            `${fmtNumber(p.data[2], 0)}万`,
        },
        data: items.map((s) => [s.duration, s.emission / 1000, s.cost / 10000, s.id]),
      },
    ],
  }
})

/** 方案对比：柱=成本（万元），线=碳排（t），tooltip 含工期 */
const compareOption = computed(() => {
  const C = dashBase.value
  const rows = schemeRows.value.slice(0, 5)
  if (rows.length === 0) return {}
  const durationByName = new Map(rows.map((r) => [r.name, r.duration]))
  return {
    backgroundColor: 'transparent',
    grid: { left: 56, right: 52, top: 32, bottom: 26 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.primary, 0.3),
      textStyle: { color: C.baseContent },
      formatter: (params: Array<{ seriesName: string; dataIndex: number; value: number }>) => {
        const name = rows[params[0]?.dataIndex ?? 0]?.name ?? ''
        const lines = params.map((p) => `${p.seriesName}：${fmtNumber(p.value, 1)}`)
        lines.push(`工期：${durationByName.get(name) ?? '—'} 天`)
        return [`<b>${name}</b>`, ...lines].join('<br/>')
      },
    },
    legend: {
      top: 0,
      textStyle: { color: withOpacity(C.baseContent, 0.65), fontSize: legendFontSize.value },
    },
    xAxis: {
      type: 'category' as const,
      data: rows.map((r) => r.name),
      axisLabel: { color: withOpacity(C.baseContent, 0.65) },
      axisLine: { lineStyle: { color: withOpacity(C.label, 0.25) } },
    },
    yAxis: [
      {
        type: 'value' as const,
        name: '万元',
        nameTextStyle: { color: withOpacity(C.baseContent, 0.5) },
        axisLabel: { color: withOpacity(C.baseContent, 0.6) },
        splitLine: { lineStyle: { color: withOpacity(C.label, 0.1) } },
      },
      {
        type: 'value' as const,
        name: 'tCO₂e',
        nameTextStyle: { color: withOpacity(C.baseContent, 0.5) },
        axisLabel: { color: withOpacity(C.baseContent, 0.6) },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '成本',
        type: 'bar' as const,
        barMaxWidth: 26,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: C.cyan },
              { offset: 1, color: C.blue },
            ],
          },
        },
        data: rows.map((r) => Math.round(r.costWan * 10) / 10),
      },
      {
        name: '碳排',
        type: 'line' as const,
        yAxisIndex: 1,
        smooth: true,
        symbolSize: 6,
        lineStyle: { width: 2, color: C.amber },
        itemStyle: { color: C.amber },
        data: rows.map((r) => Math.round(r.emissionT * 10) / 10),
      },
    ],
  }
})

const showcaseChartOption = computed(() => {
  if (chartMode.value === 'gantt') return ganttOption.value
  if (chartMode.value === 'scatter') return scatterOption.value
  return compareOption.value
})

// ─── 物化碳排趋势：物化汇总 + 三阶段曲线（日/月/年） ───────
const embodiedGranularity = ref<'day' | 'month' | 'year'>('month')
const EMBODIED_OPTIONS = [
  { value: 'day', label: '日' },
  { value: 'month', label: '月' },
  { value: 'year', label: '年' },
] as const

const embodiedPeriodItems = computed(() =>
  embodiedGranularity.value === 'day' ? dayStats.periodItems.value : periodItems.value,
)

const embodiedSeries = computed(() => {
  const items = embodiedPeriodItems.value
  // 周期 → 槽位合计（kg）
  const byPeriod = new Map<string, { label: string; slots: Record<StageSlot, number> }>()
  for (const it of items) {
    const d = new Date(it.period)
    const label =
      embodiedGranularity.value === 'day'
        ? `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
        : it.period.slice(0, 7)
    const entry = byPeriod.get(label) ?? { label, slots: { production: 0, transport: 0, construction: 0 } }
    const slot = stageSlotOf(it.bucket)
    if (slot) entry.slots[slot] += it.emission
    byPeriod.set(label, entry)
  }
  let rows = Array.from(byPeriod.values()).sort((a, b) => a.label.localeCompare(b.label))
  // 年视图：按年份求和
  if (embodiedGranularity.value === 'year') {
    const byYear = new Map<string, { label: string; slots: Record<StageSlot, number> }>()
    for (const r of rows) {
      const year = r.label.slice(0, 4)
      const entry = byYear.get(year) ?? {
        label: `${year}年`,
        slots: { production: 0, transport: 0, construction: 0 },
      }
      for (const slot of ['production', 'transport', 'construction'] as StageSlot[]) {
        entry.slots[slot] += r.slots[slot]
      }
      byYear.set(year, entry)
    }
    rows = Array.from(byYear.values()).sort((a, b) => a.label.localeCompare(b.label))
  }
  return rows.map((r) => ({
    period: r.label,
    production: r.slots.production / 1000,
    transport: r.slots.transport / 1000,
    construction: r.slots.construction / 1000,
    total: (r.slots.production + r.slots.transport + r.slots.construction) / 1000,
  }))
})

const embodiedOption = computed(() => {
  const C = dashBase.value
  const rows = embodiedSeries.value
  if (rows.length === 0) return {}
  const line = (
    name: string,
    data: number[],
    color: string,
    opts: { width?: number; dashed?: boolean } = {},
  ) => ({
    name,
    type: 'line' as const,
    smooth: true,
    symbol: 'none',
    lineStyle: { width: opts.width ?? 2, color, type: opts.dashed ? ('dashed' as const) : ('solid' as const) },
    itemStyle: { color },
    data,
  })
  return {
    backgroundColor: 'transparent',
    grid: { left: 52, right: 18, top: 34, bottom: 26 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.primary, 0.3),
      textStyle: { color: C.baseContent },
      valueFormatter: (v: number) => `${fmtNumber(v, 2)} t`,
    },
    legend: {
      top: 0,
      textStyle: { color: withOpacity(C.baseContent, 0.65), fontSize: legendFontSize.value },
    },
    xAxis: {
      type: 'category' as const,
      data: rows.map((r) => r.period),
      axisLine: { lineStyle: { color: withOpacity(C.label, 0.25) } },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
    },
    yAxis: {
      type: 'value' as const,
      name: 'tCO₂e',
      nameTextStyle: { color: withOpacity(C.baseContent, 0.5) },
      splitLine: { lineStyle: { color: withOpacity(C.label, 0.1) } },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
    },
    series: [
      line('物化汇总', rows.map((r) => Math.round(r.total * 100) / 100), C.amber, { width: 2.5 }),
      line('建材生产', rows.map((r) => Math.round(r.production * 100) / 100), C.cyan),
      line('建材运输', rows.map((r) => Math.round(r.transport * 100) / 100), C.emerald),
      line('建筑建造', rows.map((r) => Math.round(r.construction * 100) / 100), C.violet),
    ],
  }
})

const isEmbodiedEmpty = computed(
  () => embodiedGranularity.value === 'day' && embodiedSeries.value.length === 0,
)

// ─── 项目信息（施工中青色、历时金色） ──────────────────────
const STATUS_TEXT: Record<string, string> = {
  PLANNING: '计划中',
  CONSTRUCTION: '施工中',
  COMPLETED: '已完成',
}
const elapsedDays = computed(() => {
  const start = project.value?.actual_start_date ?? project.value?.planned_start_date
  if (!start) return null
  const days = Math.floor((Date.now() - new Date(start).getTime()) / 86400000)
  return days >= 0 ? days : null
})
const projectInfoRows = computed(() => [
  { label: '项目名称', value: project.value?.name ?? '—' },
  { label: '建设单位', value: '—' },
  { label: '施工单位', value: '—' },
])

// ─── 用能碳排趋势：用电 / 用水 / 用油 切换 ────────────────
const energyType = ref<'electricity' | 'water' | 'oil'>('electricity')
const ENERGY_OPTIONS = [
  { value: 'electricity', label: '用电碳排' },
  { value: 'water', label: '用水碳排' },
  { value: 'oil', label: '用油碳排' },
] as const

const ENERGY_MATCH: Record<'electricity' | 'water' | 'oil', string> = {
  electricity: '电',
  water: '水',
  oil: '油',
}

/** 月度某类用能碳排（t），桶名含关键字匹配 */
const energySeries = computed(() => {
  const kw = ENERGY_MATCH[energyType.value]
  const byPeriod = new Map<string, number>()
  for (const it of periodItems.value) {
    if (!(it.bucket ?? '').includes(kw)) continue
    const label = it.period.slice(0, 7)
    byPeriod.set(label, (byPeriod.get(label) ?? 0) + it.emission)
  }
  return Array.from(byPeriod.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([period, kg]) => ({ period, t: kg / 1000 }))
})

const energyOption = computed(() => {
  const C = dashBase.value
  const rows = energySeries.value
  if (rows.length === 0) return {}
  const name = ENERGY_OPTIONS.find((o) => o.value === energyType.value)?.label ?? ''
  return {
    backgroundColor: 'transparent',
    grid: { left: 52, right: 18, top: 30, bottom: 26 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.primary, 0.3),
      textStyle: { color: C.baseContent },
      valueFormatter: (v: number) => `${fmtNumber(v, 2)} t`,
    },
    xAxis: {
      type: 'category' as const,
      data: rows.map((r) => r.period),
      axisLine: { lineStyle: { color: withOpacity(C.label, 0.25) } },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
    },
    yAxis: {
      type: 'value' as const,
      name: 'tCO₂e',
      nameTextStyle: { color: withOpacity(C.baseContent, 0.5) },
      splitLine: { lineStyle: { color: withOpacity(C.label, 0.1) } },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
    },
    series: [
      {
        name,
        type: 'line' as const,
        smooth: true,
        symbolSize: 5,
        lineStyle: { width: 2, color: C.cyan },
        itemStyle: { color: C.cyan },
        areaStyle: {
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: withOpacity(C.cyan, 0.25) },
              { offset: 1, color: withOpacity(C.cyan, 0) },
            ],
          },
        },
        data: rows.map((r) => Math.round(r.t * 100) / 100),
      },
    ],
  }
})

// ─── 用能分布：用电/用水/用油 + 机械碳排排名 ───────────────
const energyStat = (kw: string) => {
  const kg = byBucket.value
    .filter((b) => (b.bucket ?? '').includes(kw))
    .reduce((s, b) => s + b.emissionKg, 0)
  return kg / 1000
}
const energyCards = computed(() => [
  { label: '用电碳排', valueT: energyStat('电'), icon: 'bolt' },
  { label: '用水碳排', valueT: energyStat('水'), icon: 'water_drop' },
  { label: '用油碳排', valueT: energyStat('油'), icon: 'oil_barrel' },
])

const machineryRank = computed(() => {
  const total = totalEmissionTon.value
  return byResource.value
    .filter((r) => r.category === 'machinery')
    .sort((a, b) => b.emissionKg - a.emissionKg)
    .slice(0, 5)
    .map((r) => ({
      name: r.resourceName,
      valueT: r.emissionKg / 1000,
      pct: total > 0 ? Math.round(((r.emissionKg / 1000) / total) * 100) : 0,
    }))
})
</script>

<template>
  <div class="dash">
    <!-- 顶部标题栏：左侧 天气+时间点 | 居中标题 | 右侧 项目切换 / 返回平台 / 时间 -->
    <header class="dash-top">
      <div class="dash-top-side">
        <span class="dash-weather">
          <span class="material-symbols-outlined icon-sm text-cyan">partly_cloudy_day</span>
          {{ weatherText }}
          <span class="dash-clock">{{ timePoint }}</span>
        </span>
      </div>
      <div class="dash-head">
        <h1 class="dash-title">
          <span class="wing wing-left" aria-hidden="true" />
          施工碳排放多目标优化数据看板
          <span class="wing wing-right" aria-hidden="true" />
        </h1>
      </div>
      <div class="dash-top-side right">
        <select
          class="dash-select"
          :value="currentProjectIdStr"
          aria-label="切换项目"
          @change="switchProject(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="opt in projectOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <button type="button" class="dash-back" @click="goBack">
          <span class="material-symbols-outlined icon-sm">arrow_back</span>
          返回平台
        </button>
        <span class="dash-time">{{ dateText }}</span>
      </div>
    </header>

    <!-- 三栏网格：中栏通栏跨第一二行（六指标长条 + 项目综合展示），
         底行三卡：方案推荐 / 物化碳排趋势 / 用能分布（同高、顶部对齐） -->
    <div class="dash-cols">
      <!-- 第一行：累计碳排放 | 六指标长条 | 项目信息 -->
      <section class="dash-panel area-summary flex flex-col">
        <h2 class="pt"><span class="pt-text">累计碳排放</span></h2>
        <div class="flex items-baseline gap-2 flex-wrap">
          <span class="num-big">{{ fmtNumber(totalEmissionTon, 1) }}</span>
          <span class="num-unit">tCO₂e</span>
          <span v-if="emissionLimit !== null" class="tag-limit" :class="overLimit ? 'over' : 'ok'">
            {{ overLimit ? '超标' : '不超标' }}
          </span>
        </div>
        <div class="flex-1 flex flex-col justify-evenly mt-2">
          <div v-for="(row, i) in stageRows" :key="row.name" class="stage-row">
            <div class="flex items-center gap-2">
              <span class="stage-no" :class="{ hot: i === 0 }">{{ i + 1 }}</span>
              <span class="stage-name">{{ row.name }}</span>
              <span class="stage-val">{{ fmtNumber(row.valueT, 1) }} t</span>
              <span class="stage-pct">{{ row.pct }}%</span>
            </div>
            <div class="stage-bar">
              <i :style="{ width: `${Math.max(row.pct, 2)}%` }" />
            </div>
          </div>
        </div>
      </section>

      <!-- 中栏（跨第一二行）：六指标长条在上，项目综合展示向下占满其余空间 -->
      <div class="area-mid">
        <section class="metric-strip area-metrics">
          <div v-for="(k, i) in kpis" :key="k.label" class="metric" :class="{ first: i === 0 }">
            <div class="flex items-center gap-1.5">
              <span class="material-symbols-outlined icon-sm text-cyan">{{ k.icon }}</span>
              <span class="mk">{{ k.label }}</span>
            </div>
            <div class="mv">
              {{ k.value }}<small v-if="k.unit"> {{ k.unit }}</small>
            </div>
          </div>
        </section>

        <section class="dash-panel area-showcase flex flex-col">
          <h2 class="pt"><span class="pt-text">项目综合展示</span></h2>
          <div class="pt-tools">
            <template v-if="showcaseMode === 'chart'">
              <select
                v-model="chartMode"
                class="chart-select"
                aria-label="切换图表"
              >
                <option v-for="o in CHART_OPTIONS" :key="o.value" :value="o.value">
                  {{ o.label }}
                </option>
              </select>
            </template>
            <SegmentControl
              v-model="showcaseMode"
              :options="[...SHOWCASE_OPTIONS]"
              size="sm"
              aria-label="切换展示内容"
            />
          </div>
          <div v-if="showcaseMode === 'image'" class="showcase-frame">
            <img
              v-if="projectImage"
              :src="projectImage"
              :alt="`${project?.name ?? ''} 项目图片`"
              class="absolute inset-0 h-full w-full object-cover"
            />
            <div
              v-else
              class="absolute inset-0 flex items-center justify-center text-sm"
              style="color: #8fb3d4; opacity: .7"
            >
              请到「项目信息」页上传项目图片
            </div>
          </div>
          <div v-else class="showcase-frame">
            <VChart :option="showcaseChartOption" autoresize class="w-full h-full" />
          </div>
        </section>
      </div>

      <section class="dash-panel area-info flex flex-col">
        <h2 class="pt"><span class="pt-text">项目信息</span></h2>
        <div class="info-rows">
          <div v-for="row in projectInfoRows" :key="row.label" class="info-row">
            <span class="ik">{{ row.label }}</span>
            <span class="iv truncate">{{ row.value }}</span>
          </div>
          <div class="info-row">
            <span class="ik">项目阶段</span>
            <span class="iv status-tag">{{ STATUS_TEXT[project?.status ?? ''] ?? '—' }}</span>
          </div>
          <div class="info-row">
            <span class="ik">历时天数</span>
            <span class="iv days">{{ elapsedDays === null ? '—' : elapsedDays }}<small> 天</small></span>
          </div>
        </div>
      </section>

      <!-- 第二行：碳排放构成 | 中栏（综合展示） | 用能碳排趋势 -->
      <section class="dash-panel area-composition flex flex-col">
        <h2 class="pt"><span class="pt-text">碳排放构成</span></h2>
        <div class="pt-tools">
          <SegmentControl
            v-model="compositionMode"
            :options="[...COMPOSITION_OPTIONS]"
            size="sm"
            aria-label="切换构成维度"
          />
        </div>
        <div v-if="compositionData.some((i) => i.kg > 0)" class="chart-box">
          <VChart :option="compositionOption" autoresize class="w-full h-full" />
        </div>
        <p v-else class="empty-tip">暂无数据</p>
      </section>

      <section class="dash-panel area-trend flex flex-col">
        <h2 class="pt"><span class="pt-text">用能碳排趋势</span></h2>
        <div class="pt-tools">
          <SegmentControl
            v-model="energyType"
            :options="[...ENERGY_OPTIONS]"
            size="sm"
            aria-label="切换用能类型"
          />
        </div>
        <div v-if="energySeries.length > 0" class="chart-box">
          <VChart :option="energyOption" autoresize class="w-full h-full" />
        </div>
        <p v-else class="empty-tip">暂无数据</p>
      </section>

      <!-- 底行：方案推荐 | 物化碳排趋势 | 用能分布（三卡同高、顶部对齐） -->
      <section class="dash-panel area-scheme flex flex-col">
        <h2 class="pt"><span class="pt-text">方案推荐</span></h2>
        <div v-if="schemeRows.length > 0" class="scheme-table">
          <div class="scheme-tr scheme-th">
            <span>方案</span><span>工期</span><span>成本</span><span>碳排</span><span>结论</span>
          </div>
          <div v-for="s in schemeRows" :key="s.id" class="scheme-tr">
            <span class="scheme-name-cell">{{ s.name }}</span>
            <span>{{ fmtNumber(s.duration, 0) }}天</span>
            <span>{{ fmtNumber(s.costWan, 0) }}万</span>
            <span>{{ fmtNumber(s.emissionT, 0) }}t</span>
            <span>
              <span v-if="s.recommended" class="tag-rec">推荐</span>
              <span v-else class="text-faint">可行</span>
            </span>
          </div>
        </div>
        <p v-else class="empty-tip">{{ isPlanMissing ? '暂无方案数据' : '加载中…' }}</p>
      </section>

      <section class="dash-panel area-embodied flex flex-col">
        <h2 class="pt"><span class="pt-text">物化碳排趋势</span></h2>
        <div class="pt-tools">
          <SegmentControl
            v-model="embodiedGranularity"
            :options="[...EMBODIED_OPTIONS]"
            size="sm"
            aria-label="切换粒度"
          />
        </div>
        <p v-if="isEmbodiedEmpty" class="empty-tip">暂无日数据</p>
        <div v-else-if="embodiedSeries.length > 0" class="chart-box">
          <VChart :option="embodiedOption" autoresize class="w-full h-full" />
        </div>
        <p v-else class="empty-tip">暂无数据</p>
      </section>

      <section class="dash-panel area-distribution flex flex-col">
        <h2 class="pt"><span class="pt-text">用能分布</span></h2>
        <div class="energy-cards">
          <div v-for="e in energyCards" :key="e.label" class="energy-card">
            <span class="material-symbols-outlined icon-sm text-cyan">{{ e.icon }}</span>
            <div>
              <div class="ek">{{ e.label }}</div>
              <div class="ev">{{ fmtNumber(e.valueT, 1) }}<small> t</small></div>
            </div>
          </div>
        </div>
        <div class="rank-head">机械碳排排名</div>
        <div v-if="machineryRank.length > 0" class="rank">
          <div v-for="(r, i) in machineryRank" :key="r.name" class="rank-row">
            <span class="rank-no" :class="{ hot: i < 3 }">{{ i + 1 }}</span>
            <span class="rank-name truncate">{{ r.name }}</span>
            <span class="rank-bar"><i :style="{ width: `${Math.max(r.pct, 2)}%` }" /></span>
            <span class="rank-val">{{ fmtNumber(r.valueT, 1) }} t</span>
          </div>
        </div>
        <p v-else class="empty-tip">暂无机械碳排数据</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* ── 设计令牌：背景 #050E1F · 卡片半透明深蓝 · 边框 #17426F
 * 主文字 #D8E9F8 · 次级 #8FB3D4 · 强调 #2EE6FF · 成功 #36E39A · 提醒 #FFC53D */
.dash {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 0.75rem 1rem 1rem;
  background:
    radial-gradient(1200px 380px at 50% -10%, rgb(46 230 255 / 0.08), transparent 60%),
    #050e1f;
  color: #d8e9f8;
  overflow: hidden;
}

/* ── 顶部标题栏 ── */
.dash-top {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 1rem;
  padding: 2px 0 12px;
  flex-shrink: 0;
}
.dash-top-side {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.dash-top-side.right {
  justify-content: flex-end;
}
.dash-time {
  font-size: 13px;
  color: #8fb3d4;
  letter-spacing: 0.04em;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.dash-weather {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #d8e9f8;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.dash-clock {
  color: #2ee6ff;
  font-weight: 600;
}
.dash-head {
  text-align: center;
}
.dash-title {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
  font-size: 25px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #fff;
  background: linear-gradient(180deg, #ffffff, #8fb3ff);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  white-space: nowrap;
}
.wing {
  width: 110px;
  height: 14px;
  flex-shrink: 0;
  background:
    linear-gradient(90deg, transparent, rgb(46 230 255 / 0.75)) left center / 100% 1px no-repeat,
    linear-gradient(90deg, transparent, rgb(46 230 255 / 0.35)) left 5px / 72% 1px no-repeat;
}
.wing-right {
  transform: scaleX(-1);
}
.dash-select,
.dash-back {
  width: 132px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 8px;
  background: rgb(12 34 64 / 0.85);
  border: 1px solid #17426f;
  color: #d8e9f8;
  font-size: 12.5px;
  white-space: nowrap;
}
.dash-select {
  padding: 0 8px;
  outline: none;
  text-overflow: ellipsis;
}
.dash-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
}
.dash-back:hover {
  border-color: #2ee6ff;
  color: #ffffff;
}

/* ── 三栏网格（各行跨栏对齐）
 * 中栏为一个跨第一、二行的通栏：内部纵向排 六指标长条 + 项目综合展示，
 * 综合展示占满指标条下方直至底行顶部的全部高度；
 * 底行三卡（方案推荐 / 物化碳排趋势 / 用能分布）同高、顶部对齐 */
.dash-cols {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr) 380px;
  grid-template-rows: auto 1.4fr 1fr;
  grid-template-areas:
    'summary mid info'
    'composition mid trend'
    'scheme embodied distribution';
  gap: 10px;
}
.area-mid {
  grid-area: mid;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
}
.area-summary { grid-area: summary; }
.area-info { grid-area: info; }
.area-composition { grid-area: composition; }
.area-trend { grid-area: trend; }
.area-scheme { grid-area: scheme; }
.area-embodied { grid-area: embodied; }
.area-distribution { grid-area: distribution; }
@media (max-width: 1280px) {
  .dash {
    height: auto;
    overflow: visible;
  }
  .dash-cols {
    grid-template-columns: 1fr;
    grid-template-rows: none;
    grid-template-areas:
      'mid'
      'summary'
      'composition'
      'trend'
      'scheme'
      'embodied'
      'distribution'
      'info';
  }
  .wing {
    display: none;
  }
  .showcase-frame {
    min-height: 260px;
  }
}

/* ── 卡片：半透明深蓝底 + 细描边 + 标题条 + 局部角线 ── */
.dash-panel,
.metric-strip {
  position: relative;
  background: linear-gradient(180deg, rgb(12 34 64 / 0.85), rgb(10 27 51 / 0.9));
  border: 1px solid #17426f;
  border-radius: 10px;
  padding: 12px 14px;
  min-width: 0;
}
.dash-panel::before,
.dash-panel::after,
.metric-strip::before,
.metric-strip::after {
  content: '';
  position: absolute;
  width: 14px;
  height: 14px;
  pointer-events: none;
}
.dash-panel::before,
.metric-strip::before {
  top: -1px;
  left: -1px;
  border-top: 2px solid #2ee6ff;
  border-left: 2px solid #2ee6ff;
  border-top-left-radius: 10px;
}
.dash-panel::after,
.metric-strip::after {
  bottom: -1px;
  right: -1px;
  border-bottom: 2px solid #2ee6ff;
  border-right: 2px solid #2ee6ff;
  border-bottom-right-radius: 10px;
}

.pt {
  font-size: 15px;
  font-weight: 600;
  color: #d8e9f8;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-shrink: 0;
}
/* 标题样式（设计稿标题条）：渐变竖条 + 右侧拖尾光线 */
.pt-text {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  letter-spacing: 0.04em;
}
.pt-text::before {
  content: '';
  width: 4px;
  height: 15px;
  border-radius: 2px;
  background: linear-gradient(180deg, #2ee6ff, #2563eb);
}
.pt-text::after {
  content: '';
  width: 48px;
  height: 1px;
  background: linear-gradient(90deg, rgb(46 230 255 / 0.8), transparent);
}
/* 卡片内工具条：标题下方单独一行，右对齐 */
.pt-tools {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
}
/* 图表切换下拉选（深色大屏风格，与 .dash-select 同族、高度贴合分段控件 sm） */
.chart-select {
  height: 26px;
  padding: 0 8px;
  border-radius: 6px;
  background: rgb(12 34 64 / 0.85);
  border: 1px solid #17426f;
  color: #d8e9f8;
  font-size: 12px;
  outline: none;
  cursor: pointer;
}
.chart-select:hover,
.chart-select:focus {
  border-color: #2ee6ff;
}
.chart-box {
  flex: 1;
  min-height: 120px;
}
.empty-tip {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8fb3d4;
  opacity: 0.7;
  font-size: 13px;
}
.text-cyan {
  color: #2ee6ff;
}
.text-faint {
  color: #8fb3d4;
  opacity: 0.7;
}

/* ── 六指标长条（82px，单外框 + 细分隔线） ── */
.metric-strip {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  height: 82px;
  flex-shrink: 0;
  padding: 0;
}
.metric {
  padding: 0 14px;
  border-left: 1px solid rgb(23 66 111 / 0.9);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  min-width: 0;
}
.metric.first {
  border-left: none;
}
@media (max-width: 900px) {
  .metric-strip {
    grid-template-columns: repeat(3, 1fr);
    height: auto;
    min-height: 82px;
  }
  .metric {
    padding: 10px 14px;
  }
  .metric:nth-child(4) {
    border-left: none;
  }
}
.mk {
  font-size: 13px;
  color: #8fb3d4;
  white-space: nowrap;
}
.mv {
  font-size: 24px;
  font-weight: 700;
  color: #ffffff;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.mv small {
  font-size: 12px;
  font-weight: 500;
  color: #8fb3d4;
}

/* ── 项目综合展示（填充中栏剩余高度，顶部即六指标长条下方） ── */
.area-showcase {
  flex: 1;
  min-height: 0;
}
.showcase-frame {
  position: relative;
  flex: 1;
  min-height: 0;
  border-radius: 8px;
  border: 1px solid #17426f;
  overflow: hidden;
  background: rgb(10 27 51 / 0.6);
}

/* ── 累计碳排放 ── */
.num-big {
  font-size: 30px;
  font-weight: 700;
  color: #ffffff;
  font-variant-numeric: tabular-nums;
}
.num-unit {
  font-size: 14px;
  color: #8fb3d4;
}
.tag-limit {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 10px;
  margin-left: auto;
}
.tag-limit.ok {
  color: #36e39a;
  background: rgb(54 227 154 / 0.12);
}
.tag-limit.over {
  color: #ff7a7a;
  background: rgb(245 108 108 / 0.14);
}
.stage-row {
  padding: 8px 0;
}
.stage-row + .stage-row {
  border-top: 1px dashed rgb(23 66 111 / 0.8);
}
.stage-no {
  width: 18px;
  height: 18px;
  border-radius: 5px;
  background: rgb(255 255 255 / 0.08);
  color: #8fb3d4;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
}
.stage-no.hot {
  background: linear-gradient(135deg, #2ee6ff, #2563eb);
  color: #fff;
}
.stage-name {
  font-size: 15px;
  color: #d8e9f8;
}
.stage-val {
  font-size: 19px;
  font-weight: 600;
  color: #ffffff;
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}
.stage-pct {
  font-size: 13px;
  color: #8fb3d4;
  width: 40px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.stage-bar {
  margin-top: 6px;
  height: 9px;
  border-radius: 5px;
  background: rgb(255 255 255 / 0.07);
  overflow: hidden;
}
.stage-bar i {
  display: block;
  height: 100%;
  border-radius: 5px;
  background: linear-gradient(90deg, #2ee6ff, #2563eb);
}

/* ── 方案推荐表 ── */
.scheme-table {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  font-size: 13px;
}
.scheme-tr {
  display: grid;
  grid-template-columns: 1.1fr 1fr 1fr 1fr 0.8fr;
  align-items: center;
  padding: 7px 4px;
  color: #d8e9f8;
  font-variant-numeric: tabular-nums;
}
.scheme-tr + .scheme-tr {
  border-top: 1px dashed rgb(23 66 111 / 0.8);
}
.scheme-th {
  color: #8fb3d4;
  font-size: 12px;
}
.scheme-name-cell {
  color: #ffffff;
  font-weight: 600;
}
.tag-rec {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 10px;
  color: #36e39a;
  background: rgb(54 227 154 / 0.12);
}

/* ── 项目信息（施工中青色 / 历时金色） ── */
.info-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 2px;
}
.info-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.ik {
  font-size: 15px;
  color: #8fb3d4;
  flex-shrink: 0;
}
.iv {
  font-size: 16px;
  color: #d8e9f8;
  min-width: 0;
}
.status-tag {
  color: #2ee6ff;
  font-weight: 600;
}
.iv.days {
  font-size: 20px;
  font-weight: 700;
  color: #ffc53d;
  font-variant-numeric: tabular-nums;
}
.iv.days small {
  font-size: 13px;
  font-weight: 500;
  color: #8fb3d4;
}

/* ── 用能分布 ── */
.energy-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 10px;
  flex-shrink: 0;
}
.energy-card {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgb(255 255 255 / 0.04);
  border: 1px solid #17426f;
  border-radius: 8px;
  padding: 8px 10px;
}
.ek {
  font-size: 11px;
  color: #8fb3d4;
}
.ev {
  font-size: 17px;
  font-weight: 600;
  color: #ffffff;
  font-variant-numeric: tabular-nums;
}
.ev small {
  font-size: 11px;
  font-weight: 500;
  color: #8fb3d4;
}
.rank-head {
  font-size: 13px;
  color: #8fb3d4;
  margin-bottom: 4px;
  flex-shrink: 0;
}
.rank {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
}
.rank-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 2px;
}
.rank-no {
  width: 18px;
  height: 18px;
  border-radius: 5px;
  background: rgb(255 255 255 / 0.08);
  color: #8fb3d4;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
}
.rank-no.hot {
  background: linear-gradient(135deg, #2ee6ff, #2563eb);
  color: #fff;
}
.rank-name {
  font-size: 13px;
  color: #d8e9f8;
  width: 110px;
  flex-shrink: 0;
}
.rank-bar {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: rgb(255 255 255 / 0.07);
  overflow: hidden;
}
.rank-bar i {
  display: block;
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, #2ee6ff, #2563eb);
}
.rank-val {
  font-size: 13px;
  color: #ffffff;
  width: 72px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
</style>
