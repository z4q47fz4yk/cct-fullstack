<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import TagPieChartCard from '@/components/chart/TagPieChartCard.vue'
import LoadingState from '@/components/common/LoadingState.vue'
import { useChartApi, type ChartPieMetric } from '@/composables/useChartApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { fmtNumber } from '@/utils/format'

definePage({
  meta: {
    title: '碳排放分布',
    icon: 'donut_small',
    showInNav: true,
    parentName: '/project/[projectId]/insights',
    group: '评价阶段',
    navOrder: 1,
  },
})

const { charts, isLoading } = useChartApi()
const { currentProjectId } = useProjectContext()

const metric = ref<ChartPieMetric>('emission')
const metricOptions: ReadonlyArray<SegmentOption<ChartPieMetric>> = [
  { value: 'emission', label: '碳排放', icon: 'eco' },
  { value: 'cost', label: '成本', icon: 'payments' },
]

// 各图表合计（TagPieChartCard 上报，数值单位跟随 metric）
const summaries = reactive<Record<number, number>>({})

function onSummary(payload: { chartId: number; totalKg: number }) {
  summaries[payload.chartId] = payload.totalKg
}

watch(
  () => charts.value.map((c) => c.id).join(','),
  (ids) => {
    const valid = new Set(ids ? ids.split(',').map(Number) : [])
    for (const key of Object.keys(summaries)) {
      if (!valid.has(Number(key))) delete summaries[Number(key)]
    }
  },
)

const totalValue = computed(() => Object.values(summaries).reduce((sum, v) => sum + v, 0))
</script>

<template>
  <div class="h-full flex flex-col gap-4 overflow-y-auto">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-lg font-semibold text-base-content">碳排放分布</h1>
        <p class="text-xs text-fg-subtle mt-0.5">
          按「设置 → 碳排放图表」定义的标签切片聚合（实际用量口径），可切换碳排放 / 成本
        </p>
      </div>
      <SegmentControl v-model="metric" :options="metricOptions" />
    </div>

    <LoadingState v-if="isLoading" variant="skeleton" class="h-56" />

    <div v-else-if="charts.length === 0" class="panel py-10 text-center">
      <div
        class="w-14 h-14 rounded-full bg-base-300/60 flex items-center justify-center mx-auto mb-3"
      >
        <span class="material-symbols-outlined icon-2xl text-fg-subtle">donut_small</span>
      </div>
      <p class="text-sm text-fg-muted">尚未配置标签图表</p>
      <p class="text-xs text-fg-subtle mt-1">
        前往
        <RouterLink :to="`/project/${currentProjectId}/settings/charts`" class="link link-primary">
          设置 → 碳排放图表
        </RouterLink>
        配置切片创建饼图
      </p>
    </div>

    <template v-else>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TagPieChartCard
          v-for="c in charts"
          :key="c.id"
          :chart="c"
          :metric="metric"
          @summary="onSummary"
        />
      </div>

      <div class="panel px-4 py-3 flex items-center gap-3">
        <span class="material-symbols-outlined text-primary icon-md shrink-0">pie_chart</span>
        <div class="flex-1 min-w-0">
          <p class="text-[11px] text-fg-subtle">
            {{ metric === 'emission' ? '碳排放合计' : '成本合计' }}
          </p>
          <p class="font-mono text-sm font-semibold text-base-content">
            {{
              metric === 'emission'
                ? `${fmtNumber(totalValue / 1000, 2)} tCO₂e`
                : `${fmtNumber(totalValue / 10000, 2)} 万元`
            }}
          </p>
        </div>
        <span
          class="text-[11px] font-mono px-2 py-1 rounded-full bg-primary/12 text-primary shrink-0"
        >
          {{ charts.length }} 个图表
        </span>
      </div>
    </template>
  </div>
</template>
