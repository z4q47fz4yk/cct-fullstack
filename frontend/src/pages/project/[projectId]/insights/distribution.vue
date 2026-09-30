<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useQueryCache } from '@pinia/colada'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import TagPieChartCard from '@/components/chart/TagPieChartCard.vue'
import LoadingState from '@/components/common/LoadingState.vue'
import { useChartApi, type ChartPieMetric } from '@/composables/useChartApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useSnapshotManualRefresh, useSnapshotRefreshInfo } from '@/composables/useSnapshotApi'
import { notifyError, notifySuccess } from '@/composables/useToast'
import { fmtNumber } from '@/utils/format'
import { formatHttpError } from '@/utils/error'

definePage({
  meta: {
    title: '碳排放分布',
    description: '按「设置 → 碳排放图表」定义的标签切片聚合，可切换碳排放 / 成本',
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

// ──── 数据新鲜度（物化视图聚合最长约 30 分钟延迟，提供手动刷新入口） ────
const queryCache = useQueryCache()
const { info: snapshotInfo, refresh: refreshSnapshotInfo } = useSnapshotRefreshInfo()
const { refreshSnapshot, isRefreshing } = useSnapshotManualRefresh()

async function handleManualRefresh() {
  try {
    await refreshSnapshot({ path: { project_id: currentProjectId.value! } })
    // 饼图数据来自物化视图：强制刷新后立即重查
    await queryCache.invalidateQueries({ key: ['getChartPieData'] })
    await refreshSnapshotInfo()
    notifySuccess({ title: '数据已刷新', description: '碳排放分布已按最新用量重新聚合' })
  } catch (e) {
    console.error('Manual snapshot refresh failed:', e)
    notifyError({ title: '刷新失败', description: formatHttpError(e) })
  }
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <div class="h-full flex flex-col gap-4 overflow-y-auto">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <!-- 数据新鲜度提示：录入后图表可能滞后于物化视图刷新周期 -->
      <div class="flex items-center gap-2 text-xs text-fg-subtle min-w-0 flex-wrap">
        <span class="material-symbols-outlined icon-sm shrink-0">schedule</span>
        <span>数据由物化视图聚合，录入后最长约 30 分钟延迟</span>
        <span v-if="snapshotInfo?.lastRefreshedAt" class="font-mono">
          上次刷新 {{ fmtTime(snapshotInfo.lastRefreshedAt) }}
        </span>
        <button
          class="btn btn-ghost btn-xs shrink-0"
          :disabled="isRefreshing"
          @click="handleManualRefresh"
        >
          <span v-if="isRefreshing" class="loading loading-spinner loading-xs"></span>
          <span v-else class="material-symbols-outlined icon-sm">refresh</span>
          立即刷新
        </button>
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
