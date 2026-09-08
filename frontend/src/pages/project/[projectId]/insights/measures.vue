<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import { usePlanApi } from '@/composables/usePlanApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { notifySuccess } from '@/composables/useToast'
import { fmtNumber } from '@/utils/format'
import { getThemeColors } from '@/utils/themeColors'
import type { MeasureResp, MeasureStatus } from '@/client/types.gen'

use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

definePage({
  meta: {
    title: '低碳措施',
    description:
      '添加类（光伏等负碳因子资源）即时抵扣 · 替换类按资源流逐日计算 · 状态在施工阶段维护',
    icon: 'energy_savings_leaf',
    showInNav: true,
    parentName: '/project/[projectId]/insights',
    group: '评价阶段',
    navOrder: 3,
  },
})

const { measures, isLoadingMeasures, updateMeasureItem, refreshMeasures } = usePlanApi()
const { currentProjectId } = useProjectContext()
const C = getThemeColors()

const resourcesQuery = useQuery(() => ({
  ...listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { page: 1, per_page: FETCH_ALL_PAGE_SIZE },
  }),
  enabled: !!currentProjectId.value,
}))
const resourceById = computed(
  () => new Map((resourcesQuery.state.value?.data?.items ?? []).map((r) => [r.id, r])),
)

function measureName(m: MeasureResp): string {
  return m.resourceIds.map((id) => resourceById.value.get(id)?.name ?? `资源#${id}`).join(' → ')
}

const totals = computed(() => {
  let estimated = 0
  let actual = 0
  for (const m of measures.value) {
    estimated += m.estimatedSaving
    actual += m.actualSaving
  }
  return { estimated, actual, difference: actual - estimated }
})

const statusOptions: Record<MeasureStatus, string> = {
  PLANNED: '计划中',
  IMPLEMENTED: '已实施',
  ABANDONED: '未实施',
}

async function changeStatus(m: MeasureResp, status: MeasureStatus) {
  try {
    await updateMeasureItem(m.id, { status })
    await refreshMeasures()
    notifySuccess({ title: '状态已更新' })
  } catch (e) {
    console.error('Update measure status failed:', e)
  }
}

const chartOption = computed(() => ({
  grid: { left: 48, right: 16, top: 32, bottom: 28 },
  tooltip: { trigger: 'axis' },
  legend: {
    data: ['预估节碳', '实际节碳'],
    textStyle: { color: C.label },
    top: 0,
  },
  xAxis: {
    type: 'category',
    data: measures.value.map((m) => m.resourceIds.join('→')),
    axisLabel: { color: C.label, interval: 0, width: 100, overflow: 'truncate' },
  },
  yAxis: {
    type: 'value',
    name: 't',
    axisLabel: { color: C.label, formatter: (v: number) => fmtNumber(v / 1000, 1) },
    splitLine: { lineStyle: { color: C.splitLine } },
  },
  series: [
    {
      name: '预估节碳',
      type: 'bar',
      data: measures.value.map((m) => m.estimatedSaving),
      itemStyle: { color: C.info },
      barMaxWidth: 18,
    },
    {
      name: '实际节碳',
      type: 'bar',
      data: measures.value.map((m) => m.actualSaving),
      itemStyle: { color: C.success },
      barMaxWidth: 18,
    },
  ],
}))
</script>

<template>
  <div class="h-full flex flex-col gap-4 overflow-y-auto">
    <div class="grid grid-cols-3 gap-4">
      <div class="panel px-4 py-3">
        <p class="text-[11px] text-fg-subtle">预估节碳合计</p>
        <p class="text-lg font-semibold font-num text-info">
          {{ fmtNumber(totals.estimated / 1000, 2)
          }}<span class="text-xs text-fg-subtle font-normal"> t</span>
        </p>
      </div>
      <div class="panel px-4 py-3">
        <p class="text-[11px] text-fg-subtle">实际节碳合计</p>
        <p class="text-lg font-semibold font-num text-success">
          {{ fmtNumber(totals.actual / 1000, 2)
          }}<span class="text-xs text-fg-subtle font-normal"> t</span>
        </p>
      </div>
      <div class="panel px-4 py-3">
        <p class="text-[11px] text-fg-subtle">差额（实际 − 预估）</p>
        <p
          class="text-lg font-semibold font-num"
          :class="totals.difference <= 0 ? 'text-success' : 'text-warning'"
        >
          {{ totals.difference > 0 ? '+' : '' }}{{ fmtNumber(totals.difference / 1000, 2) }}
          <span class="text-xs text-fg-subtle font-normal"> t</span>
        </p>
      </div>
    </div>

    <div class="panel p-4">
      <h2 class="text-sm font-semibold text-base-content mb-3">措施清单</h2>
      <div v-if="isLoadingMeasures" class="space-y-2">
        <div v-for="i in 3" :key="i" class="skeleton h-12 w-full rounded-lg"></div>
      </div>
      <ChartEmptyState
        v-else-if="measures.length === 0"
        icon="energy_savings_leaf"
        title="暂无低碳措施"
        description="请到「计划编制」页添加光伏或设备替换措施"
      />
      <div v-else class="overflow-x-auto">
        <table class="table table-sm">
          <thead>
            <tr>
              <th>措施</th>
              <th>类型</th>
              <th>状态</th>
              <th class="table-num">预估节碳 t</th>
              <th class="table-num">实际节碳 t</th>
              <th class="table-num">差额 t</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in measures" :key="m.id">
              <td class="font-medium max-w-64 truncate">{{ measureName(m) }}</td>
              <td>
                <span
                  class="text-xs font-medium px-2 py-0.5 rounded-full"
                  :class="m.kind === 'ADD' ? 'bg-success/15 text-success' : 'bg-info/15 text-info'"
                >
                  {{ m.kind === 'ADD' ? '添加' : '替换' }}
                </span>
              </td>
              <td>
                <select
                  :value="m.status"
                  class="select select-xs select-bordered"
                  @change="
                    changeStatus(m, ($event.target as HTMLSelectElement).value as MeasureStatus)
                  "
                >
                  <option v-for="(label, value) in statusOptions" :key="value" :value="value">
                    {{ label }}
                  </option>
                </select>
              </td>
              <td class="table-num">{{ fmtNumber(m.estimatedSaving / 1000, 2) }}</td>
              <td class="table-num">{{ fmtNumber(m.actualSaving / 1000, 2) }}</td>
              <td
                class="table-num"
                :class="m.savingDifference <= 0 ? 'text-success' : 'text-warning'"
              >
                {{ m.savingDifference > 0 ? '+' : '' }}{{ fmtNumber(m.savingDifference / 1000, 2) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel p-4">
      <h2 class="text-sm font-semibold text-base-content mb-2">预估 vs 实际节碳</h2>
      <div v-if="measures.length > 0" class="h-56">
        <VChart :option="chartOption" autoresize />
      </div>
    </div>
  </div>
</template>
