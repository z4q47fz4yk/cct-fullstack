<script setup lang="ts">
/**
 * 施工进度（分析洞察）页
 *
 * 主图 = Plotly 三区（ProgressTimelinePlot）：
 *   上 甘特（日历日期 x 轴：计划/实际横道 + 每日累计进度线）
 *   中 碳排柱（ACTUAL，粒度 day/week/month 可切，按维度堆叠）
 *   下 天气折线（气温/降水）
 * 计划数据来自基线 tasks 快照（start/duration 相对锚点偏移），
 * 逐日进度来自 /task/progress/timeline，碳排来自 /resource-usage/stats/carbon。
 */
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BaseModal from '@/components/ui/BaseModal.vue'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import ProgressTimelinePlot from '@/components/schedule/ProgressTimelinePlot.vue'
import type {
  CarbonBarDatum,
  PlotGranularity,
  ProgressPlotData,
  TimelineTaskRow,
  WeatherDatum,
} from '@/composables/useProgressPlotFigure'
import { useInsightsStore } from '@/stores/insights'
import { useProjectContext } from '@/composables/useProjectContext'
import { useProjectApi } from '@/composables/useProjectApi'
import { usePlanApi } from '@/composables/usePlanApi'
import { useProgressApi } from '@/composables/useProgressApi'
import { useWeatherApi } from '@/composables/useWeatherApi'
import { useCarbonStats, type CarbonGranularity } from '@/composables/useCarbonStats'
import { useConfirm } from '@/composables/useConfirm'
import { notifySuccess, notifyError } from '@/composables/useToast'
import { fmtEmission, fmtWanYuan, fmtNumber } from '@/utils/format'
import { getThemeColors, getCategoryColor, getSliceColor } from '@/utils/themeColors'
import { todayIsoLocal } from '@/utils/date'
import { formatHttpError } from '@/utils/error'
import type { WeatherResp } from '@/client/types.gen'
import { categoryConfigMap, type ResourceCategory } from '@/types/resource'

definePage({
  meta: {
    title: '施工进度',
    icon: 'timeline',
    showInNav: true,
    parentName: '/project/[projectId]/insights',
    group: '施工阶段',
    navOrder: 1,
  },
})

const store = useInsightsStore()
const router = useRouter()
const { currentProjectId } = useProjectContext()
const { project } = useProjectApi()
const { plan } = usePlanApi()
const { projectSummaries, isLoadingProjectSummaries, progressTimeline } = useProgressApi()
const { weather, createRecord, updateRecord, deleteRecord, refresh, syncWeather, isSyncing } =
  useWeatherApi()
const { confirmDanger } = useConfirm()
const C = getThemeColors()

const MS_DAY = 86_400_000
// 本地时区“今天”（toISOString 为 UTC，跨时区会取到昨天）
const todayIso = todayIsoLocal

// ──── 锚点：实际开工（空回退拟开工） ───────────────────────
const anchorDate = computed<string | null>(
  () => project.value?.actual_start_date ?? project.value?.planned_start_date ?? null,
)

/** 锚点 + 偏移天数 → YYYY-MM-DD */
function anchorPlusDays(days: number): string {
  const a = new Date(anchorDate.value ?? todayIso())
  const d = new Date(a.getTime() + days * MS_DAY)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

// ──── 顶部统计 ─────────────────────────────────────────────
const summaryByTask = computed(() => new Map(projectSummaries.value.map((s) => [s.taskId, s])))

const taskRows = computed(() => {
  const planMap = new Map((plan.value?.tasks ?? []).map((t) => [t.taskId, t]))
  const seen = new Set<number>()
  const rows: {
    taskId: number
    code: string
    name: string
    planned?: { start: number; duration: number }
    summary?: {
      currentPercent: number
      isCompleted: boolean
      actualStartDate: string | null
      actualCompletionDate: string | null
      series: { date: string; percent: number }[]
    }
  }[] = []
  const tlMap = new Map((progressTimeline.value?.items ?? []).map((s) => [s.taskId, s]))
  for (const t of store.tasks) {
    seen.add(t.id)
    const tl = tlMap.get(t.id)
    rows.push({
      taskId: t.id,
      code: t.code,
      name: t.name,
      planned: planMap.get(t.id)
        ? { start: planMap.get(t.id)!.start, duration: planMap.get(t.id)!.duration }
        : undefined,
      summary: tl
        ? {
            currentPercent: tl.currentPercent,
            isCompleted: tl.isCompleted,
            actualStartDate: tl.actualStartDate ?? null,
            actualCompletionDate: tl.actualCompletionDate ?? null,
            series: tl.series.map((p) => ({ date: p.date, percent: p.percent })),
          }
        : undefined,
    })
  }
  for (const p of plan.value?.tasks ?? []) {
    if (seen.has(p.taskId)) continue
    const tl = tlMap.get(p.taskId)
    rows.push({
      taskId: p.taskId,
      code: p.code,
      name: p.name,
      planned: { start: p.start, duration: p.duration },
      summary: tl
        ? {
            currentPercent: tl.currentPercent,
            isCompleted: tl.isCompleted,
            actualStartDate: tl.actualStartDate ?? null,
            actualCompletionDate: tl.actualCompletionDate ?? null,
            series: tl.series.map((s) => ({ date: s.date, percent: s.percent })),
          }
        : undefined,
    })
  }
  return rows
})

const completedCount = computed(() => projectSummaries.value.filter((s) => s.isCompleted).length)
const overallPercent = computed(() => {
  const list = projectSummaries.value
  if (list.length === 0) return 0
  return Math.round(list.reduce((sum, s) => sum + s.currentPercent, 0) / list.length)
})

const plannedDuration = computed(() => plan.value?.totalDuration ?? null)

// ──── 时间粒度（日/周/月）：用户可切，按跨度自动收紧默认 ────
const granOptions: ReadonlyArray<SegmentOption<PlotGranularity>> = [
  { value: 'day', label: '日' },
  { value: 'week', label: '周' },
  { value: 'month', label: '月' },
]
const granularity = ref<CarbonGranularity>('month')

// 收集全部日期做跨度和 x 轴范围
const allDates = computed<string[]>(() => {
  const out = new Set<string>()
  for (const t of plan.value?.tasks ?? []) {
    if (anchorDate.value) {
      out.add(anchorPlusDays(t.start))
      out.add(anchorPlusDays(t.start + t.duration))
    }
  }
  for (const tl of progressTimeline.value?.items ?? []) {
    if (tl.actualStartDate) out.add(tl.actualStartDate)
    if (tl.actualCompletionDate) out.add(tl.actualCompletionDate)
    for (const p of tl.series) out.add(p.date)
  }
  out.add(todayIso())
  return Array.from(out).sort()
})

const spanDays = computed<number>(() => {
  const ds = allDates.value
  if (ds.length === 0) return 0
  const a = new Date(ds[0]!).getTime()
  const b = new Date(ds[ds.length - 1]!).getTime()
  return (b - a) / MS_DAY
})

const defaultGranularity = computed<CarbonGranularity>(() => {
  const d = spanDays.value
  if (d <= 40) return 'day'
  if (d <= 40 * 7) return 'week'
  return 'month'
})
let userPickedGranularity = false
watch(
  defaultGranularity,
  (g) => {
    if (!userPickedGranularity) granularity.value = g
  },
  { immediate: true },
)
function pickGranularity(g: CarbonGranularity) {
  userPickedGranularity = true
  granularity.value = g
}

// ──── 碳排（粒度随切换变化） ───────────────────────────────
const { periodItems, totalEmissionTon, totalCost } = useCarbonStats(() => granularity.value)

// ──── 碳排维度切换 ─────────────────────────────────────────
type EmissionDim = 'total' | 'category' | 'resource'
const emissionDim = ref<EmissionDim>('total')
const dimOptions: ReadonlyArray<SegmentOption<EmissionDim>> = [
  { value: 'total', label: '总量', icon: 'co2' },
  { value: 'category', label: '排放类别', icon: 'category' },
  { value: 'resource', label: '资源', icon: 'inventory_2' },
]

const CATEGORY_ORDER: ResourceCategory[] = ['labor', 'machinery', 'material', 'transport', 'others']

// 碳排 Top 5 资源（其他归入「其他」段）
const resourceTop = computed(() => {
  const m = new Map<number, { name: string; kg: number }>()
  for (const x of periodItems.value) {
    const cur = m.get(x.resourceId) ?? { name: x.resourceName, kg: 0 }
    cur.kg += x.emission
    m.set(x.resourceId, cur)
  }
  return Array.from(m.entries())
    .sort((a, b) => b[1].kg - a[1].kg)
    .slice(0, 5)
    .map(([id, v]) => ({ id, ...v }))
})

/** 碳排柱：按 period 分桶，桶内按当前维度切段 */
const carbonBars = computed<CarbonBarDatum[]>(() => {
  const byPeriod = new Map<
    string,
    { total: number; cats: Map<ResourceCategory, number>; res: Map<number, number> }
  >()
  for (const x of periodItems.value) {
    let b = byPeriod.get(x.period)
    if (!b) {
      b = { total: 0, cats: new Map(), res: new Map() }
      byPeriod.set(x.period, b)
    }
    b.total += x.emission
    b.cats.set(x.category, (b.cats.get(x.category) ?? 0) + x.emission)
    b.res.set(x.resourceId, (b.res.get(x.resourceId) ?? 0) + x.emission)
  }
  const topIds = new Set(resourceTop.value.map((r) => r.id))
  const nameOf = new Map(resourceTop.value.map((r) => [r.id, r.name]))
  const periods = Array.from(byPeriod.keys()).sort()

  return periods.map((period) => {
    const b = byPeriod.get(period)!
    const segments: CarbonBarDatum['segments'] = []
    if (emissionDim.value === 'category') {
      for (const cat of CATEGORY_ORDER) {
        const kg = b.cats.get(cat) ?? 0
        if (kg !== 0) {
          segments.push({
            name: categoryConfigMap[cat].label,
            value: kg,
            color: getCategoryColor(cat),
          })
        }
      }
    } else if (emissionDim.value === 'resource') {
      let idx = 0
      let others = 0
      for (const [rid, kg] of Array.from(b.res.entries()).sort((a, b2) => b2[1] - a[1])) {
        if (topIds.has(rid)) {
          segments.push({
            name: nameOf.get(rid) ?? `资源#${rid}`,
            value: kg,
            color: getSliceColor(idx++),
          })
        } else {
          others += kg
        }
      }
      if (others !== 0) segments.push({ name: '其他', value: others, color: C.label })
    } else {
      segments.push({ name: '碳排', value: b.total, color: C.violet })
    }
    // 稳定顺序：按 value 降序（总量单段不受影响）
    if (emissionDim.value !== 'total') segments.sort((a, b2) => b2.value - a.value)
    return { period, segments }
  })
})

/** 碳排图例（页面层展示） */
const emissionLegend = computed<{ name: string; color: string }[]>(() => {
  if (emissionDim.value === 'category') {
    return CATEGORY_ORDER.map((c) => ({
      name: categoryConfigMap[c].label,
      color: getCategoryColor(c),
    }))
  }
  if (emissionDim.value === 'resource') {
    return [
      ...resourceTop.value.map((r, i) => ({ name: r.name, color: getSliceColor(i) })),
      { name: '其他', color: C.label },
    ]
  }
  return [{ name: '碳排', color: C.violet }]
})

// ──── 天气点（日期 → 日历 x） ──────────────────────────────
const weatherDatum = computed<WeatherDatum[]>(() =>
  weather.value.map((w) => ({
    day: w.date,
    temperatureC: w.temperatureC ?? null,
    precipitationMm: w.precipitationMm ?? null,
  })),
)

// ──── 组装 Plotly 主图数据 ─────────────────────────────────
const plotRows = computed<TimelineTaskRow[]>(() =>
  taskRows.value.map((r) => {
    const planStart = r.planned ? anchorPlusDays(r.planned.start) : null
    const planEnd = r.planned ? anchorPlusDays(r.planned.start + r.planned.duration) : null
    const s = r.summary
    return {
      taskId: r.taskId,
      code: r.code,
      name: r.name,
      planStart,
      planEnd,
      actualStart: s?.actualStartDate ?? null,
      actualEnd: s?.actualCompletionDate ?? (s?.actualStartDate ? todayIso() : null),
      series: (s?.series ?? []).map((p) => [p.date, p.percent] as [string, number]),
      currentPercent: s?.currentPercent ?? 0,
      isCompleted: s?.isCompleted ?? false,
    }
  }),
)

const xMin = computed<string>(() => allDates.value[0] ?? todayIso())
const xMax = computed<string>(() => {
  const last = allDates.value[allDates.value.length - 1] ?? todayIso()
  // 末尾留一点 padding（+3 天）
  return new Date(new Date(last).getTime() + 3 * MS_DAY).toISOString().slice(0, 10)
})

const plotData = computed<ProgressPlotData>(() => ({
  tasks: plotRows.value,
  carbon: carbonBars.value,
  weather: weatherDatum.value,
  granularity: granularity.value,
  minDate: xMin.value,
  maxDate: xMax.value,
  colors: C,
  todayIso: todayIso(),
}))

const hasAnyData = computed(
  () =>
    !isLoadingProjectSummaries.value &&
    (plotRows.value.length > 0 || carbonBars.value.length > 0 || weatherDatum.value.length > 0),
)

// ──── 天气弹窗（手工录入 + Open-Meteo 同步） ──────────────
const showWeatherModal = ref(false)
const editingWeatherId = ref<number | null>(null)
const weatherForm = reactive({
  date: '',
  precipitationMm: null as number | null,
  temperatureC: null as number | null,
  sunshineHours: null as number | null,
})
const weatherFormError = ref<string | null>(null)

function openWeatherCreate() {
  editingWeatherId.value = null
  Object.assign(weatherForm, {
    date: '',
    precipitationMm: null,
    temperatureC: null,
    sunshineHours: null,
  })
  weatherFormError.value = null
  showWeatherModal.value = true
}

function openWeatherEdit(w: WeatherResp) {
  editingWeatherId.value = w.id
  Object.assign(weatherForm, {
    date: w.date,
    precipitationMm: w.precipitationMm,
    temperatureC: w.temperatureC,
    sunshineHours: w.sunshineHours,
  })
  weatherFormError.value = null
  showWeatherModal.value = true
}

async function handleSubmitWeather() {
  weatherFormError.value = null
  if (!weatherForm.date) {
    weatherFormError.value = '请选择日期'
    return
  }
  const body = {
    date: weatherForm.date,
    precipitationMm: weatherForm.precipitationMm,
    temperatureC: weatherForm.temperatureC,
    sunshineHours: weatherForm.sunshineHours,
  }
  try {
    if (editingWeatherId.value) {
      await updateRecord(editingWeatherId.value, body)
    } else {
      await createRecord(body)
    }
    await refresh()
    showWeatherModal.value = false
    notifySuccess({ title: editingWeatherId.value ? '天气已更新' : '天气已录入' })
  } catch (e) {
    weatherFormError.value = formatHttpError(e)
    console.error('Save weather failed:', e)
  }
}

async function handleDeleteWeather(w: WeatherResp) {
  const r = await confirmDanger('确定删除该日天气记录吗？', '删除天气')
  if (!r.confirmed) return
  try {
    await deleteRecord(w.id)
    await refresh()
  } catch (e) {
    console.error('Delete weather failed:', e)
  }
}

/** 同步范围：项目开工（实际/拟）至今天；省略则后端按默认窗口。 */
async function handleSyncWeather() {
  const coords = project.value?.latitude ?? null
  if (coords == null || project.value?.longitude == null) {
    const r = await confirmDanger(
      '项目未设置经纬度，无法自动同步历史天气。是否前往「项目信息」填写纬度/经度？',
      '缺少经纬度',
    )
    if (r.confirmed && currentProjectId.value !== null) {
      router.push({
        name: '/project/[projectId]/settings/info',
        params: { projectId: currentProjectId.value },
      })
    }
    return
  }
  try {
    const res = await syncWeather({})
    await refresh()
    notifySuccess({ title: '天气同步完成', description: res.message })
  } catch (e) {
    notifyError({ title: '天气同步失败', description: formatHttpError(e) })
    console.error('Sync weather failed:', e)
  }
}

const emissionLegendVisible = computed(() => emissionDim.value !== 'total')
</script>

<template>
  <div class="h-full flex flex-col gap-4 overflow-y-auto">
    <!-- 顶部统计 -->
    <div class="grid grid-cols-4 gap-3">
      <div class="panel px-4 py-3">
        <p class="text-[11px] text-fg-subtle">计划工期</p>
        <p class="text-lg font-semibold font-num text-base-content">
          {{ plannedDuration !== null ? fmtNumber(plannedDuration, 1) : '—' }}
          <span class="text-xs text-fg-subtle font-normal">天</span>
        </p>
      </div>
      <div class="panel px-4 py-3">
        <p class="text-[11px] text-fg-subtle">完成度</p>
        <p class="text-lg font-semibold font-num text-primary">{{ overallPercent }}%</p>
      </div>
      <div class="panel px-4 py-3">
        <p class="text-[11px] text-fg-subtle">总碳排（实际）</p>
        <p class="text-lg font-semibold font-num text-violet">
          {{ fmtNumber(totalEmissionTon, 2)
          }}<span class="text-xs text-fg-subtle font-normal"> t</span>
        </p>
      </div>
      <div class="panel px-4 py-3">
        <p class="text-[11px] text-fg-subtle">总成本（实际）</p>
        <p class="text-lg font-semibold font-num text-info">
          {{ fmtWanYuan(totalCost) }}<span class="text-xs text-fg-subtle font-normal"> 万</span>
        </p>
      </div>
    </div>

    <!-- 全景主图 -->
    <div class="panel p-3 flex flex-col gap-3">
      <div class="flex items-center justify-between gap-4 flex-wrap">
        <div class="flex items-center gap-3 flex-wrap">
          <SegmentControl v-model="emissionDim" :options="dimOptions" />
          <SegmentControl
            :model-value="granularity"
            :options="granOptions"
            @update:model-value="pickGranularity"
          />
        </div>
        <div class="flex items-center gap-4 flex-wrap">
          <!-- 甘特图例 -->
          <div class="flex items-center gap-3 text-xs">
            <span class="flex items-center gap-1.5"
              ><i class="w-2.5 h-2.5 rounded-full inline-block" :style="{ background: C.label }"></i
              >计划</span
            >
            <span class="flex items-center gap-1.5"
              ><i class="w-2.5 h-2.5 rounded-full inline-block" :style="{ background: C.info }"></i
              >实际进行中</span
            >
            <span class="flex items-center gap-1.5"
              ><i
                class="w-2.5 h-2.5 rounded-full inline-block"
                :style="{ background: C.success }"
              ></i
              >实际完成</span
            >
            <span class="flex items-center gap-1.5"
              ><i class="w-2.5 h-2.5 rounded-full inline-block" :style="{ background: C.accel }"></i
              >每日进度</span
            >
          </div>
          <!-- 碳排维度图例，在 plotly 图中已存在 -->
          <div v-if="false" class="flex items-center gap-3 text-xs">
            <span v-for="item in emissionLegend" :key="item.name" class="flex items-center gap-1.5">
              <i
                class="w-2.5 h-2.5 rounded-full inline-block"
                :style="{ background: item.color }"
              ></i>
              {{ item.name }}
            </span>
          </div>
          <button class="btn btn-ghost btn-sm" @click="openWeatherCreate">
            <span class="material-symbols-outlined icon-sm">partly_cloudy_day</span>
            天气数据
          </button>
        </div>
      </div>

      <ChartEmptyState
        v-if="!hasAnyData"
        icon="timeline"
        title="暂无施工数据"
        description="录入工序进度、资源用量或天气数据后展示全景时间线"
      />
      <ProgressTimelinePlot v-else :data="plotData" :height="640" />
    </div>

    <!-- 天气录入/同步弹窗 -->
    <BaseModal v-model:open="showWeatherModal" title="天气数据（日）" class="max-w-2xl">
      <div class="space-y-4">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <p class="text-sm text-fg-muted">
            手工录入某日天气，或用 Open-Meteo 拉取项目所在地的历史日均温 / 降水 / 光照。
          </p>
          <button class="btn btn-ghost btn-sm" :disabled="isSyncing" @click="handleSyncWeather">
            <span class="material-symbols-outlined icon-sm">sync</span>
            {{ isSyncing ? '同步中…' : '自动同步历史' }}
          </button>
        </div>
        <div class="grid grid-cols-4 gap-3">
          <label class="fieldset">
            <span class="fieldset-legend">日期</span>
            <input v-model="weatherForm.date" type="date" class="input input-bordered" />
          </label>
          <label class="fieldset">
            <span class="fieldset-legend">降水 mm</span>
            <input
              v-model.number="weatherForm.precipitationMm"
              type="number"
              class="input input-bordered"
            />
          </label>
          <label class="fieldset">
            <span class="fieldset-legend">平均气温 ℃</span>
            <input
              v-model.number="weatherForm.temperatureC"
              type="number"
              class="input input-bordered"
            />
          </label>
          <label class="fieldset">
            <span class="fieldset-legend">光照 h</span>
            <input
              v-model.number="weatherForm.sunshineHours"
              type="number"
              class="input input-bordered"
            />
          </label>
        </div>
        <p v-if="weatherFormError" class="text-xs text-error">{{ weatherFormError }}</p>

        <div v-if="weather.length > 0" class="overflow-x-auto">
          <table class="table table-sm">
            <thead>
              <tr>
                <th>日期</th>
                <th class="table-num">降水 mm</th>
                <th class="table-num">气温 ℃</th>
                <th class="table-num">光照 h</th>
                <th>来源</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="w in weather" :key="w.id">
                <td class="font-num">{{ w.date }}</td>
                <td class="table-num">{{ w.precipitationMm ?? '—' }}</td>
                <td class="table-num">{{ w.temperatureC ?? '—' }}</td>
                <td class="table-num">{{ w.sunshineHours ?? '—' }}</td>
                <td>
                  <span class="text-xs" :class="w.isSynced ? 'text-fg-subtle' : 'text-primary'">
                    {{ w.isSynced ? '自动同步' : '手工' }}
                  </span>
                </td>
                <td class="text-right whitespace-nowrap">
                  <button class="btn btn-ghost btn-xs" @click="openWeatherEdit(w)">编辑</button>
                  <button class="btn btn-ghost btn-xs text-error" @click="handleDeleteWeather(w)">
                    删除
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="text-sm text-fg-muted">
          暂无天气记录。可手工录入或点击「自动同步历史」按项目经纬度拉取。
        </p>
      </div>
      <template #actions>
        <button class="btn btn-ghost" @click="showWeatherModal = false">关闭</button>
        <button class="btn btn-primary" @click="handleSubmitWeather">
          {{ editingWeatherId ? '保存修改' : '添加' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>
