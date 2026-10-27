<script setup lang="ts">
/**
 * 碳排数据看板 - 全屏深色大屏（设计稿 view-dark）
 *
 * 进入本页时临时将文档主题切为深色（大屏为暗色设计，与全局明暗无关），
 * 离开时恢复；图表经 getThemeColors() 自动取深色配色。
 *
 * 数据全部复用现有只读聚合接口：
 * - useCarbonStats   累计碳排 / 成本 / 月度趋势 / 类别构成 / TopN 资源
 * - useComplianceApi 计划基线 vs 实际（月度对照）
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import TopEmittersChart from '@/components/common/TopEmittersChart.vue'
import { useCarbonStats } from '@/composables/useCarbonStats'
import { useComplianceApi } from '@/composables/useComplianceApi'
import { useProjectApi } from '@/composables/useProjectApi'
import { getThemeColors, withOpacity, getCategoryColor, refreshThemeColors } from '@/utils/themeColors'
import { fmtNumber } from '@/utils/format'
import type { ResourceCategory } from '@/client/types.gen'

use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

definePage({
  meta: {
    title: '碳排数据看板',
    showInNav: false,
    parentName: '/project/[projectId]/statistics',
    navOrder: 1,
    /** 全屏大屏：不渲染侧边栏/顶栏（ProjectLayout 消费） */
    fullscreen: true,
  },
})

// ─── 临时深色主题（进入切深色，离开恢复） ───────────────────
const previousTheme = ref<string | null>(null)

onMounted(() => {
  previousTheme.value = document.documentElement.dataset.theme ?? null
  document.documentElement.dataset.theme = 'starglass'
  refreshThemeColors()
})

onBeforeUnmount(() => {
  if (previousTheme.value) {
    document.documentElement.dataset.theme = previousTheme.value
  } else {
    delete document.documentElement.dataset.theme
  }
  refreshThemeColors()
})

// ─── 数据 ────────────────────────────────────────────────
const { totalEmissionTon, totalCost, totalMonths, totalResources, byMonth, byCategory, byResource } =
  useCarbonStats()
const { data: compliance, isNoPlan } = useComplianceApi()
const { project } = useProjectApi()

// Top N 高排放资源（取前 8）
const topEmitters = computed(() =>
  [...byResource.value].sort((a, b) => b.emissionKg - a.emissionKg).slice(0, 8),
)

// 工序完成率（来自计划践行度数据）
const taskProgress = computed(() => {
  const rows = compliance.value?.taskRows
  if (!rows || rows.length === 0) return null
  const done = rows.filter((r) => r.isCompleted).length
  return Math.round((done / rows.length) * 100)
})

const kpis = computed(() => [
  { label: '累计碳排放', value: fmtNumber(totalEmissionTon.value, 1), unit: 'tCO₂e', icon: 'eco' },
  {
    label: '累计成本',
    value: fmtNumber(totalCost.value / 10000, 1),
    unit: '万元',
    icon: 'payments',
  },
  { label: '统计周期', value: String(totalMonths.value), unit: '个月', icon: 'calendar_month' },
  {
    label: '工序完成率',
    value: taskProgress.value === null ? '—' : `${taskProgress.value}`,
    unit: taskProgress.value === null ? '' : '%',
    icon: 'fact_check',
  },
])

// ─── 月度碳排放趋势（柱 + 累计线） ──────────────────────────
const trendOption = computed(() => {
  const C = getThemeColors()
  const items = byMonth.value
  const months = items.map((m) => m.month.slice(0, 7))
  const values = items.map((m) => Math.round((m.emissionKg / 1000) * 100) / 100)
  let acc = 0
  const cumulative = values.map((v) => (acc += v))
  return {
    backgroundColor: 'transparent',
    grid: { left: 48, right: 40, top: 32, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.primary, 0.3),
      textStyle: { color: C.baseContent },
    },
    legend: {
      data: ['月度碳排放', '累计碳排放'],
      textStyle: { color: withOpacity(C.baseContent, 0.65) },
      top: 0,
    },
    xAxis: {
      type: 'category',
      data: months,
      axisLine: { lineStyle: { color: withOpacity(C.label, 0.25) } },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
    },
    yAxis: {
      type: 'value',
      name: 'tCO₂e',
      nameTextStyle: { color: withOpacity(C.baseContent, 0.5) },
      splitLine: { lineStyle: { color: withOpacity(C.label, 0.1) } },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
    },
    series: [
      {
        name: '月度碳排放',
        type: 'bar',
        data: values,
        barMaxWidth: 22,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            type: 'linear' as const,
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: C.cyan },
              { offset: 1, color: C.blue },
            ],
          },
        },
      },
      {
        name: '累计碳排放',
        type: 'line',
        data: cumulative,
        smooth: true,
        symbolSize: 5,
        lineStyle: { width: 2, color: C.amber },
        itemStyle: { color: C.amber },
        areaStyle: {
          color: {
            type: 'linear' as const,
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: withOpacity(C.amber, 0.25) },
              { offset: 1, color: withOpacity(C.amber, 0) },
            ],
          },
        },
      },
    ],
  }
})

// ─── 类别构成环图 ─────────────────────────────────────────
const categoryOption = computed(() => {
  const C = getThemeColors()
  const items = byCategory.value
  if (items.length === 0) return {}
  const CATEGORY_NAMES: Record<ResourceCategory, string> = {
    labor: '人工',
    machinery: '机械',
    material: '材料',
    transport: '运输',
    others: '其他',
  }
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
      right: 8,
      top: 'middle',
      textStyle: { color: withOpacity(C.baseContent, 0.65) },
    },
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['38%', '50%'],
        avoidLabelOverlap: true,
        label: { show: false },
        data: items.map((i) => ({
          name: CATEGORY_NAMES[i.category] ?? i.category,
          value: Math.round(i.emissionKg),
          itemStyle: { color: getCategoryColor(i.category) },
        })),
      },
    ],
  }
})

// ─── 计划 vs 实际（月度碳排） ───────────────────────────────
const planActualOption = computed(() => {
  const C = getThemeColors()
  const rows = compliance.value?.monthly ?? []
  if (rows.length === 0) return {}
  return {
    backgroundColor: 'transparent',
    grid: { left: 48, right: 40, top: 32, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.primary, 0.3),
      textStyle: { color: C.baseContent },
    },
    legend: {
      data: ['计划碳排', '实际碳排'],
      textStyle: { color: withOpacity(C.baseContent, 0.65) },
      top: 0,
    },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.month),
      axisLine: { lineStyle: { color: withOpacity(C.label, 0.25) } },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
    },
    yAxis: {
      type: 'value',
      name: 'tCO₂e',
      nameTextStyle: { color: withOpacity(C.baseContent, 0.5) },
      splitLine: { lineStyle: { color: withOpacity(C.label, 0.1) } },
      axisLabel: { color: withOpacity(C.baseContent, 0.6) },
    },
    series: [
      {
        name: '计划碳排',
        type: 'line',
        data: rows.map((r) => Math.round((r.plannedEmission / 1000) * 100) / 100),
        smooth: true,
        lineStyle: { width: 2, type: 'dashed' as const, color: C.violet },
        itemStyle: { color: C.violet },
        symbolSize: 5,
      },
      {
        name: '实际碳排',
        type: 'line',
        data: rows.map((r) => Math.round((r.actualEmission / 1000) * 100) / 100),
        smooth: true,
        lineStyle: { width: 2, color: C.emerald },
        itemStyle: { color: C.emerald },
        symbolSize: 5,
        areaStyle: {
          color: {
            type: 'linear' as const,
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: withOpacity(C.emerald, 0.2) },
              { offset: 1, color: withOpacity(C.emerald, 0) },
            ],
          },
        },
      },
    ],
  }
})
</script>

<template>
  <div class="dash">
    <!-- 返回平台 -->
    <button type="button" class="dash-back" @click="$router.back()">
      <span class="material-symbols-outlined icon-sm">arrow_back</span>
      返回平台
    </button>

    <!-- 标题 -->
    <header class="dash-head">
      <h1 class="dash-title">施工碳排放数据看板</h1>
      <p class="dash-sub">{{ project?.name ?? '' }} · CARBON EMISSION DASHBOARD</p>
    </header>

    <!-- KPI 行 -->
    <div class="dash-kpis">
      <div v-for="k in kpis" :key="k.label" class="kpi">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined icon-md text-cyan">{{ k.icon }}</span>
          <span class="kk">{{ k.label }}</span>
        </div>
        <div class="kv">
          {{ k.value }}<small v-if="k.unit"> {{ k.unit }}</small>
        </div>
      </div>
    </div>

    <!-- 面板网格 -->
    <div class="dash-grid">
      <section class="dash-panel dg8">
        <h2 class="pt">碳排放月度趋势</h2>
        <div class="h-64"><VChart :option="trendOption" autoresize /></div>
      </section>

      <section class="dash-panel dg4">
        <h2 class="pt">Top 高排放资源</h2>
        <TopEmittersChart
          v-if="topEmitters.length > 0"
          :top-emitters="topEmitters"
          :selected-resource-id="null"
          class="!bg-transparent !border-0 !shadow-none"
        />
        <p v-else class="empty-tip">暂无排放数据，请先录入实际资源使用量</p>
      </section>

      <section class="dash-panel dg4">
        <h2 class="pt">碳排放类别构成</h2>
        <div class="h-64"><VChart :option="categoryOption" autoresize /></div>
      </section>

      <section class="dash-panel dg8">
        <h2 class="pt">计划 vs 实际碳排放</h2>
        <div v-if="!isNoPlan && (compliance?.monthly?.length ?? 0) > 0" class="h-64">
          <VChart :option="planActualOption" autoresize />
        </div>
        <p v-else class="empty-tip">
          {{ isNoPlan ? '尚未保存施工计划基线，请到「计划编制」保存基线后查看对照' : '暂无月度数据' }}
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* ── 大屏容器：设计稿 view-dark ── */
.dash {
  position: relative;
  min-height: 100vh;
  padding: 1.25rem;
  background:
    radial-gradient(1200px 400px at 50% -10%, rgb(37 99 235 / 0.18), transparent 60%),
    #050e1f;
  color: #dbe4ff;
}

.dash-back {
  position: absolute;
  top: 1rem;
  left: 1rem;
  z-index: 5;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  border-radius: 8px;
  background: rgb(12 34 64 / 0.92);
  border: 1px solid #1f5287;
  color: #cfe9ff;
  font-size: 13.5px;
  cursor: pointer;
}
.dash-back:hover {
  border-color: #2ee6ff;
  color: #e8f6ff;
}

.dash-head {
  text-align: center;
  padding: 6px 0 18px;
}
.dash-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #fff;
  background: linear-gradient(180deg, #fff, #8fb3ff);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.dash-sub {
  font-size: 12px;
  color: #6f84c2;
  letter-spacing: 0.18em;
  margin-top: 4px;
}

/* KPI 卡 */
.dash-kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 14px;
}
@media (max-width: 1100px) {
  .dash-kpis {
    grid-template-columns: repeat(2, 1fr);
  }
}
.kpi {
  background: linear-gradient(160deg, rgb(34 211 238 / 0.12), rgb(37 99 235 / 0.06));
  border: 1px solid #263569;
  border-radius: 12px;
  padding: 14px 18px;
  position: relative;
  overflow: hidden;
}
.kpi::after {
  content: '';
  position: absolute;
  right: -20px;
  top: -20px;
  width: 90px;
  height: 90px;
  border-radius: 50%;
  background: radial-gradient(circle, rgb(34 211 238 / 0.18), transparent 70%);
}
.kk {
  font-size: 13px;
  color: #8ba0d6;
}
.kv {
  font-size: 26px;
  font-weight: 700;
  color: #fff;
  margin-top: 6px;
  font-variant-numeric: tabular-nums;
}
.kv small {
  font-size: 13px;
  font-weight: 500;
  color: #8ba0d6;
}

/* 面板网格 */
.dash-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 14px;
}
.dg4 {
  grid-column: span 4;
}
.dg8 {
  grid-column: span 8;
}
@media (max-width: 1100px) {
  .dg4,
  .dg8 {
    grid-column: span 12;
  }
}
.dash-panel {
  background: linear-gradient(180deg, rgb(23 37 84 / 0.85), rgb(15 26 60 / 0.9));
  border: 1px solid #263569;
  border-radius: 12px;
  padding: 14px 16px;
  min-width: 0;
}
.pt {
  font-size: 14px;
  font-weight: 600;
  color: #cfe0ff;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.pt::before {
  content: '';
  width: 4px;
  height: 14px;
  border-radius: 2px;
  background: #22d3ee;
}
.empty-tip {
  padding: 40px 0;
  text-align: center;
  color: #5f75b5;
  font-size: 13px;
}
</style>
