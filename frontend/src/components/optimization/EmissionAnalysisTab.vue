<script setup lang="ts">
/**
 * 碳排放分析 Tab 容器
 *
 * 组合：
 * - 4 张概览卡片（StatCard + glow variant）
 * - 月度趋势图（堆叠/折线切换）
 * - 资源类别占比环形图
 * - Top N 高排放资源横向柱状图
 *
 * 全部数据来自 useCarbonStats()，自动随 projectId 切换重新请求。
 */
import { computed, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ResourceCategory } from '@/client/types.gen'
import { categoryConfigMap } from '@/types/resource'
import { useCarbonStats } from '@/composables/useCarbonStats'
import type { TrendMode } from '@/composables/useEmissionTrendChart'
import type { ResourceEmission } from '@/composables/useCarbonStats'
import EmissionTrendChart from '@/components/common/EmissionTrendChart.vue'
import EmissionByCategoryChart from '@/components/project-overview/EmissionByCategoryChart.vue'
import TopEmittersChart from '@/components/common/TopEmittersChart.vue'
import TagChartsSection from '@/components/chart/TagChartsSection.vue'
import StatCard from '@/components/common/StatCard.vue'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import { fmtNumber } from '@/utils/format'
import { getThemeColors } from '@/utils/themeColors'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const {
  items,
  totalEmissionKg,
  totalEmissionTon,
  totalMonths,
  totalCost,
  byMonthCategory,
  byCategory,
  byBucket,
  byMonthCost,
  byResource,
  isLoading,
  isNotFound,
  error,
  refresh,
} = useCarbonStats()

// ─── 概览卡片数据 ────────────────────────────────────────────────

const avgMonthly = computed(() => {
  if (totalMonths.value === 0) return 0
  return Math.round((totalEmissionTon.value / totalMonths.value) * 10) / 10
})

const categoryCount = computed(() => byCategory.value.length)

const topResource = computed(() => byResource.value[0]?.resourceName ?? '—')

// ─── 成本卡片 ────────────────────────────────────────────────
const avgMonthlyCost = computed(() => {
  if (totalMonths.value === 0) return 0
  return totalCost.value / totalMonths.value
})

const topCostResource = computed(() => {
  const m = new Map<number, { name: string; cost: number }>()
  for (const x of items.value) {
    const cur = m.get(x.resourceId)
    if (cur) cur.cost += x.cost ?? 0
    else m.set(x.resourceId, { name: x.resourceName, cost: x.cost ?? 0 })
  }
  return Array.from(m.values()).sort((a, b) => b.cost - a.cost)[0]?.name ?? '—'
})

const waterElectricityKg = computed(() =>
  byBucket.value
    .filter((b) => b.bucket === 'water' || b.bucket === 'electricity')
    .reduce((sum, b) => sum + b.emissionKg, 0),
)

// ─── 月度成本柱状图 ─────────────────────────────────────────
const C = getThemeColors()
const monthlyCostOption = computed(() => ({
  grid: { left: 56, right: 16, top: 24, bottom: 28 },
  tooltip: {
    trigger: 'axis',
    formatter: (params: unknown) => {
      const p = params as { name: string; value: number }[]
      return `${p[0]?.name ?? ''}<br/>成本：${fmtNumber((p[0]?.value ?? 0) / 10000, 2)} 万元`
    },
  },
  xAxis: {
    type: 'category',
    data: byMonthCost.value.map((m) => m.month.slice(5, 7) + '月'),
    axisLabel: { color: C.label },
  },
  yAxis: {
    type: 'value',
    axisLabel: {
      color: C.label,
      formatter: (v: number) => `${fmtNumber(Math.round(v / 10000), 0)}万`,
    },
    splitLine: { lineStyle: { color: C.splitLine } },
  },
  series: [
    {
      type: 'bar',
      data: byMonthCost.value.map((m) => m.cost),
      itemStyle: { color: C.info, borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 26,
    },
  ],
}))

function formattedEmission(): string {
  if (totalEmissionTon.value >= 0.01) return fmtNumber(totalEmissionTon.value, 2)
  return fmtNumber(totalEmissionKg.value, 0)
}

const emissionUnit = computed(() => (totalEmissionTon.value >= 0.01 ? 'tCO₂e' : 'kgCO₂e'))

// ─── 趋势状态 ────────────────────────────────────────────────

const trendMode = ref<TrendMode>('stacked')
const selectedResourceIds = ref<number[]>([])

const availableResources = computed(() =>
  byResource.value.slice(0, 30).map((r) => ({
    id: r.resourceId,
    name: r.resourceName,
    category: r.category,
  })),
)

function ensureDefaultLineSelection() {
  if (trendMode.value === 'line' && selectedResourceIds.value.length === 0) {
    selectedResourceIds.value = byResource.value.slice(0, 3).map((r) => r.resourceId)
  }
}

function setTrendMode(m: TrendMode) {
  trendMode.value = m
  ensureDefaultLineSelection()
}

// ─── 类别筛选（联动 Top N） ────────────────────────────────

const selectedCategory = ref<ResourceCategory | null>(null)

const filteredByResource = computed<ResourceEmission[]>(() => {
  if (!selectedCategory.value) return byResource.value
  return byResource.value.filter((r) => r.category === selectedCategory.value)
})

const topN = ref<number>(10)
const topEmitters = computed(() => filteredByResource.value.slice(0, topN.value))

// ─── 联动：点击 Top N 行 → 切换趋势图 + 选中资源 ─────────

const selectedResourceId = ref<number | null>(null)

function handleSelectResource(rid: number) {
  selectedResourceId.value = rid
  trendMode.value = 'line'
  if (!selectedResourceIds.value.includes(rid)) {
    selectedResourceIds.value = [...selectedResourceIds.value, rid]
  }
}

// ─── 404 处理 ─────────────────────────────────────────────

const route = useRoute()
const router = useRouter()
const navigating = ref(false)

watch(isNotFound, async (notFound) => {
  if (notFound && !navigating.value) {
    navigating.value = true
  }
})
</script>

<template>
  <!-- 加载 / 错误 / 空状态 -->
  <div v-if="isLoading" class="flex justify-center py-8">
    <span class="loading loading-spinner loading-lg text-primary"></span>
  </div>

  <ErrorState
    v-else-if="isNotFound"
    title="暂无碳排放数据"
    description="后端未找到本项目的月度排放记录，请先在「资源使用」中录入实际使用量"
    icon="eco"
    @retry="refresh"
  />

  <ErrorState
    v-else-if="error && !isNotFound"
    title="加载失败"
    description="无法获取碳排放数据，请检查网络连接"
    @retry="refresh"
  />

  <ChartEmptyState
    v-if="items.length === 0"
    icon="eco"
    title="本项目暂无碳排放数据"
    description="录入资源使用量后即可查看碳排放分析"
  />

  <div v-else class="space-y-4">
    <!-- Row 1: 4 张概览卡片（StatCard + glow） -->
    <div class="grid grid-cols-4 gap-4 anim-fade-up">
      <StatCard
        label="累计碳排放"
        :value="formattedEmission()"
        :unit="emissionUnit"
        icon="eco"
        color="success"
        :loading="isLoading"
      />
      <StatCard
        label="月均碳排放"
        :value="avgMonthly"
        unit="tCO₂e"
        icon="avg_pace"
        color="info"
        :loading="isLoading"
      />
      <StatCard
        label="资源类别"
        :value="categoryCount"
        unit="类"
        icon="category"
        color="primary"
        :loading="isLoading"
      />
      <StatCard
        label="最高排放资源"
        :value="topResource"
        icon="trending_up"
        color="warning"
        size="sm"
        :loading="isLoading"
      />
    </div>

    <!-- Row 1.5: 成本与水电卡片 -->
    <div class="grid grid-cols-4 gap-4">
      <StatCard
        label="累计成本（名义）"
        :value="fmtNumber(totalCost / 10000, 2)"
        unit="万元"
        icon="payments"
        color="info"
        :loading="isLoading"
      />
      <StatCard
        label="月均成本"
        :value="fmtNumber(avgMonthlyCost / 10000, 2)"
        unit="万元"
        icon="avg_pace"
        color="neutral"
        :loading="isLoading"
      />
      <StatCard
        label="水电排放"
        :value="fmtNumber(waterElectricityKg / 1000, 2)"
        unit="tCO₂e"
        icon="water_drop"
        color="info"
        :loading="isLoading"
      />
      <StatCard
        label="最高成本资源"
        :value="topCostResource"
        icon="trending_up"
        color="warning"
        size="sm"
        :loading="isLoading"
      />
    </div>

    <!-- Row 2: 月度趋势 + 类别占比 -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-2">
        <EmissionTrendChart
          v-model:mode="trendMode"
          :by-month-category="byMonthCategory"
          :items="items"
          v-model:selected-resource-ids="selectedResourceIds"
          :available-resources="availableResources"
          @update:mode="setTrendMode"
        />
      </div>
      <div>
        <EmissionByCategoryChart
          :by-category="byCategory"
          :by-bucket="byBucket"
          :total-emission-kg="totalEmissionKg"
        />
      </div>
    </div>

    <!-- Row 2.5: 月度成本 -->
    <div class="panel p-4">
      <h2 class="text-sm font-semibold text-base-content mb-1">月度成本（名义）</h2>
      <p class="text-xs text-fg-subtle mb-3">实际用量 × 有效单价，按自然月聚合</p>
      <div v-if="byMonthCost.length > 0" class="h-48">
        <VChart :option="monthlyCostOption" autoresize />
      </div>
      <ChartEmptyState v-else icon="payments" title="暂无成本数据" />
    </div>

    <!-- Row 3: Top N -->
    <div>
      <TopEmittersChart
        :top-emitters="topEmitters"
        :selected-resource-id="selectedResourceId"
        @select-resource="handleSelectResource"
      />

      <div class="flex items-center gap-2 mt-3 ml-1 flex-wrap">
        <span class="text-xs text-fg-subtle">Top N:</span>
        <div class="join">
          <button
            v-for="n in [5, 10, 15]"
            :key="n"
            class="join-item btn btn-xs"
            :class="topN === n ? 'btn-primary' : 'btn-ghost'"
            @click="topN = n"
          >
            {{ n }}
          </button>
        </div>

        <span class="text-xs text-fg-subtle ml-3">类别筛选:</span>
        <select v-model="selectedCategory" class="select select-xs select-bordered bg-base-200">
          <option :value="null">全部</option>
          <option v-for="cat in byCategory" :key="cat.category" :value="cat.category">
            {{ categoryConfigMap[cat.category].label }}
          </option>
        </select>
        <button
          v-if="selectedCategory"
          class="btn btn-ghost btn-xs"
          @click="selectedCategory = null"
        >
          清除
        </button>
      </div>
    </div>

    <!-- Row 4: 标签碳排放占比（图表定义驱动） -->
    <TagChartsSection v-if="!isLoading" />
  </div>
</template>
