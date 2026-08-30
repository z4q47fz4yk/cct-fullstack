<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import ConstructionTimelineChart, {
  type EmissionBand,
  type EmissionSegment,
  type WeatherPoint,
} from '@/components/schedule/ConstructionTimelineChart.vue'
import type { GanttChartItem } from '@/components/common/GanttChart.vue'
import { useInsightsStore } from '@/stores/insights'
import { useProjectApi } from '@/composables/useProjectApi'
import { usePlanApi } from '@/composables/usePlanApi'
import { useProgressApi } from '@/composables/useProgressApi'
import { useWeatherApi } from '@/composables/useWeatherApi'
import { useCarbonStats } from '@/composables/useCarbonStats'
import { useConfirm } from '@/composables/useConfirm'
import { notifySuccess } from '@/composables/useToast'
import { fmtEmission, fmtWanYuan, fmtNumber } from '@/utils/format'
import { getThemeColors, getCategoryColor, getSliceColor } from '@/utils/themeColors'
import { todayIsoLocal } from '@/utils/date'
import { formatHttpError } from '@/utils/error'
import type { TaskProgressSummaryResp, WeatherResp } from '@/client/types.gen'
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
const { project } = useProjectApi()
const { plan } = usePlanApi()
const { projectSummaries, isLoadingProjectSummaries } = useProgressApi()
const { weather, createRecord, updateRecord, deleteRecord, refresh } = useWeatherApi()
const { items, byMonthCategory, totalEmissionTon, totalCost } = useCarbonStats()
const { confirmDanger } = useConfirm()
const C = getThemeColors()

// ──── 锚点：实际开工（空回退拟开工 / 最早碳排月份） ───────
const anchorDate = computed<string | null>(
  () => project.value?.actual_start_date ?? project.value?.planned_start_date ?? null,
)

/** 时间轴锚点：项目日期优先，缺失时回退到最早碳排月份（保证月度色带仍能对齐） */
const timelineAnchor = computed<string | null>(() => {
  if (anchorDate.value) return anchorDate.value
  const months = byMonthCategory.value.map((m) => m.month).sort()
  return months.length > 0 ? monthFirst(months[0]!) : null
})

function dayIndex(date: string): number {
  if (!timelineAnchor.value) return 0
  const a = new Date(timelineAnchor.value).getTime()
  const d = new Date(date).getTime()
  return Math.round((d - a) / 86_400_000)
}

// 本地时区“今天”（toISOString 为 UTC，跨时区会取到昨天）
const todayIso = todayIsoLocal

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
    actual?: TaskProgressSummaryResp
  }[] = []
  for (const t of store.tasks) {
    seen.add(t.id)
    rows.push({
      taskId: t.id,
      code: t.code,
      name: t.name,
      planned: planMap.get(t.id)
        ? { start: planMap.get(t.id)!.start, duration: planMap.get(t.id)!.duration }
        : undefined,
      actual: summaryByTask.value.get(t.id),
    })
  }
  for (const p of plan.value?.tasks ?? []) {
    if (seen.has(p.taskId)) continue
    rows.push({
      taskId: p.taskId,
      code: p.code,
      name: p.name,
      planned: { start: p.start, duration: p.duration },
      actual: summaryByTask.value.get(p.taskId),
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

// ──── 甘特：计划 + 实际双行 ────────────────────────────────
interface GanttMeta {
  label: string
  kind: 'planned' | 'actual'
  percent: number
}

const ganttItems = computed<GanttChartItem<GanttMeta>[]>(() => {
  const items: GanttChartItem<GanttMeta>[] = []
  for (const row of taskRows.value) {
    if (row.planned) {
      items.push({
        label: `${row.code} ${row.name}（计划）`,
        startDay: row.planned.start,
        duration: row.planned.duration,
        color: C.label,
        meta: { label: row.name, kind: 'planned', percent: 0 },
      })
    }
    const a = row.actual
    if (a && timelineAnchor.value && a.actualStartDate) {
      const end = a.actualCompletionDate ?? todayIso()
      items.push({
        label: `${row.code} ${row.name}（实际）`,
        startDay: dayIndex(a.actualStartDate),
        duration: Math.max(dayIndex(end) - dayIndex(a.actualStartDate), 0.5),
        color: a.isCompleted ? C.success : C.indigo,
        meta: { label: row.name, kind: 'actual', percent: a.currentPercent },
      })
    }
  }
  return items
})

const ganttTotalDays = computed(() => {
  let max = 0
  for (const row of taskRows.value) {
    const pEnd = row.planned ? row.planned.start + row.planned.duration : 0
    const a = row.actual
    const aEnd = a && a.actualStartDate ? dayIndex(a.actualCompletionDate ?? todayIso()) : 0
    max = Math.max(max, pEnd, aEnd)
  }
  if (timelineAnchor.value) max = Math.max(max, dayIndex(todayIso()))
  return max || 1
})

function formatGanttTooltip(item: GanttChartItem<GanttMeta>): string {
  const m = item.meta!
  return `
    <div style="font-size:12px; line-height:1.6;">
      <div style="font-weight:600; margin-bottom:4px;">${m.label}</div>
      <div>${m.kind === 'planned' ? '计划' : '实际'} · 第 ${item.startDay} 天起，共 ${item.duration} 天</div>
      ${m.kind === 'actual' ? `<div>当前进度 ${m.percent}%</div>` : ''}
    </div>
  `
}

// ──── 碳排放维度切换 ───────────────────────────────────────
type EmissionDim = 'total' | 'category' | 'resource'

const emissionDim = ref<EmissionDim>('total')
const dimOptions: ReadonlyArray<SegmentOption<EmissionDim>> = [
  { value: 'total', label: '总量', icon: 'co2' },
  { value: 'category', label: '排放类别', icon: 'category' },
  { value: 'resource', label: '资源', icon: 'inventory_2' },
]

const CATEGORY_ORDER: ResourceCategory[] = ['labor', 'machinery', 'material', 'transport', 'others']

/** 全局碳排 Top 5 资源（其他归入「其他」段） */
const resourceTop = computed(() => {
  const m = new Map<number, { name: string; kg: number }>()
  for (const x of items.value) {
    const cur = m.get(x.resourceId) ?? { name: x.resourceName, kg: 0 }
    cur.kg += x.emission
    m.set(x.resourceId, cur)
  }
  return Array.from(m.entries())
    .sort((a, b) => b[1].kg - a[1].kg)
    .slice(0, 5)
    .map(([id, v]) => ({ id, ...v }))
})

function monthParts(month: string): { y: number; m: number } {
  const parts = month.split('-').map(Number)
  return { y: parts[0] ?? 0, m: parts[1] ?? 0 }
}

function monthFirst(month: string): string {
  const { y, m } = monthParts(month)
  return `${y}-${String(m).padStart(2, '0')}-01`
}

function monthNext(month: string): string {
  const { y, m } = monthParts(month)
  const ny = m === 12 ? y + 1 : y
  const nm = m === 12 ? 1 : m + 1
  return `${ny}-${String(nm).padStart(2, '0')}-01`
}

function monthRange(month: string): { start: number; end: number } {
  const start = dayIndex(monthFirst(month))
  const end = dayIndex(monthNext(month))
  return { start: Math.max(0, start), end: Math.min(ganttTotalDays.value, end) }
}

function monthLabel(month: string): string {
  return `${monthParts(month).m}月`
}

/** 月度碳排色带（按当前维度切分） */
const bands = computed<EmissionBand[]>(() => {
  const out: EmissionBand[] = []
  if (emissionDim.value === 'resource') {
    const byMonth = new Map<string, Map<number, number>>()
    for (const x of items.value) {
      if (!byMonth.has(x.month)) byMonth.set(x.month, new Map())
      const mm = byMonth.get(x.month)!
      mm.set(x.resourceId, (mm.get(x.resourceId) ?? 0) + x.emission)
    }
    const topIds = new Set(resourceTop.value.map((r) => r.id))
    const nameOf = new Map(resourceTop.value.map((r) => [r.id, r.name]))
    for (const [month, mm] of byMonth) {
      const range = monthRange(month)
      if (range.start >= range.end) continue
      const segments: EmissionSegment[] = []
      let others = 0
      let idx = 0
      for (const [id, kg] of mm) {
        if (topIds.has(id)) {
          segments.push({
            name: nameOf.get(id) ?? `资源#${id}`,
            value: kg,
            color: getSliceColor(idx++),
          })
        } else {
          others += kg
        }
      }
      segments.sort((a, b) => b.value - a.value)
      if (others > 0) segments.push({ name: '其他', value: others, color: C.label })
      const total = Array.from(mm.values()).reduce((s, v) => s + v, 0)
      if (total > 0) {
        out.push({
          label: monthLabel(month),
          startDay: range.start,
          endDay: range.end,
          totalKg: total,
          segments,
        })
      }
    }
  } else {
    for (const m of byMonthCategory.value) {
      const range = monthRange(m.month)
      if (range.start >= range.end) continue
      const segments: EmissionSegment[] = []
      if (emissionDim.value === 'category') {
        for (const cat of CATEGORY_ORDER) {
          const kg = m.byCategory[cat]
          if (kg > 0) {
            segments.push({
              name: categoryConfigMap[cat].label,
              value: kg,
              color: getCategoryColor(cat),
            })
          }
        }
      } else {
        const total = CATEGORY_ORDER.reduce((s, cat) => s + m.byCategory[cat], 0)
        segments.push({ name: '碳排', value: total, color: C.violet })
      }
      const total = segments.reduce((s, x) => s + x.value, 0)
      if (total > 0) {
        out.push({
          label: monthLabel(m.month),
          startDay: range.start,
          endDay: range.end,
          totalKg: total,
          segments,
        })
      }
    }
  }
  return out
})

/** 碳排维度图例（页面层渲染，组件不感知维度） */
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

// ──── 天气折线（月份中点） ─────────────────────────────────
const weatherPoints = computed<WeatherPoint[]>(() =>
  weather.value.map((w) => {
    const { y, m } = monthParts(w.month)
    const mid = dayIndex(`${y}-${String(m).padStart(2, '0')}-15`)
    return {
      day: Math.min(Math.max(mid, 0), ganttTotalDays.value),
      temperatureC: w.temperatureC ?? null,
      precipitationMm: w.precipitationMm ?? null,
    }
  }),
)

// ──── 天气录入弹窗 ─────────────────────────────────────────
const showWeatherModal = ref(false)
const editingWeatherId = ref<number | null>(null)
const weatherForm = reactive({
  month: '',
  precipitationMm: null as number | null,
  temperatureC: null as number | null,
  sunshineHours: null as number | null,
})
const weatherFormError = ref<string | null>(null)

function openWeatherCreate() {
  editingWeatherId.value = null
  Object.assign(weatherForm, {
    month: '',
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
    month: w.month,
    precipitationMm: w.precipitationMm,
    temperatureC: w.temperatureC,
    sunshineHours: w.sunshineHours,
  })
  weatherFormError.value = null
  showWeatherModal.value = true
}

async function handleSubmitWeather() {
  weatherFormError.value = null
  if (!weatherForm.month) {
    weatherFormError.value = '请选择月份（每月 1 日）'
    return
  }
  const body = {
    month: weatherForm.month,
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
  const r = await confirmDanger('确定删除该月天气记录吗？', '删除天气')
  if (!r.confirmed) return
  try {
    await deleteRecord(w.id)
    await refresh()
  } catch (e) {
    console.error('Delete weather failed:', e)
  }
}
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
        <SegmentControl v-model="emissionDim" :options="dimOptions" />
        <div class="flex items-center gap-4 flex-wrap">
          <!-- 甘特图例 -->
          <div class="flex items-center gap-3 text-xs">
            <span class="flex items-center gap-1.5"
              ><i class="w-2.5 h-2.5 rounded-full inline-block" :style="{ background: C.label }"></i
              >计划</span
            >
            <span class="flex items-center gap-1.5"
              ><i
                class="w-2.5 h-2.5 rounded-full inline-block"
                :style="{ background: C.indigo }"
              ></i
              >实际进行中</span
            >
            <span class="flex items-center gap-1.5"
              ><i
                class="w-2.5 h-2.5 rounded-full inline-block"
                :style="{ background: C.success }"
              ></i
              >实际完成</span
            >
          </div>
          <!-- 碳排维度图例 -->
          <div class="flex items-center gap-3 text-xs">
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
        v-if="ganttItems.length === 0 && bands.length === 0 && !isLoadingProjectSummaries"
        icon="timeline"
        title="暂无施工数据"
        description="录入工序进度与资源用量后展示全景时间线"
      />
      <ConstructionTimelineChart
        v-else
        :gantt-items="ganttItems"
        :gantt-tooltip-formatter="formatGanttTooltip as (item: GanttChartItem<unknown>) => string"
        :gantt-label-width="190"
        :bands="bands"
        :weather="weatherPoints"
        :total-days="ganttTotalDays"
        :anchor-date="timelineAnchor"
      />
    </div>

    <!-- 天气录入弹窗 -->
    <BaseModal v-model:open="showWeatherModal" title="天气数据（月度）" class="max-w-2xl">
      <div class="space-y-4">
        <div class="grid grid-cols-4 gap-3">
          <label class="fieldset">
            <span class="fieldset-legend">月份（每月 1 日）</span>
            <input v-model="weatherForm.month" type="date" class="input input-bordered" />
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
                <th>月份</th>
                <th class="table-num">降水 mm</th>
                <th class="table-num">气温 ℃</th>
                <th class="table-num">光照 h</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="w in weather" :key="w.id">
                <td class="font-num">{{ w.month }}</td>
                <td class="table-num">{{ w.precipitationMm ?? '—' }}</td>
                <td class="table-num">{{ w.temperatureC ?? '—' }}</td>
                <td class="table-num">{{ w.sunshineHours ?? '—' }}</td>
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
