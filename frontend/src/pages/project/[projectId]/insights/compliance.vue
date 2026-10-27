<script setup lang="ts">
import { computed } from 'vue'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import { useComplianceApi } from '@/composables/useComplianceApi'
import { usePlanApi } from '@/composables/usePlanApi'
import { fmtNumber, fmtWanYuan } from '@/utils/format'
import type { ComplianceTaskRow } from '@/client/types.gen'

definePage({
  meta: {
    title: '计划践行度',
    description: '以计划编制保存的施工计划基线为基准，对比实际施工数据',
    icon: 'fact_check',
    showInNav: true,
    parentName: '/project/[projectId]/insights',
    group: '评价阶段',
    navOrder: 2,
  },
})

const { data, isLoading, isNoPlan, refresh } = useComplianceApi()
// 基线过期状态来自 GET /plans 的存储值（数据体检页手动检查后更新），此处只读
const { plan } = usePlanApi()

function statusBadge(diff: number): { label: string; cls: string } {
  const good = diff <= 0
  return good ? { label: '达标', cls: 'badge-success' } : { label: '需关注', cls: 'badge-warning' }
}

const cards = computed(() => {
  const d = data.value
  if (!d) return []
  return [
    {
      label: '总工期',
      planned: `${fmtNumber(d.plannedDuration, 1)} 天`,
      actual:
        d.actualDuration !== null && d.actualDuration !== undefined
          ? `${fmtNumber(d.actualDuration, 1)} 天`
          : '—',
      diff:
        d.actualDuration !== null && d.actualDuration !== undefined
          ? `${d.actualDuration - d.plannedDuration > 0 ? '+' : ''}${fmtNumber(d.actualDuration - d.plannedDuration, 1)} 天`
          : '—',
      badge:
        d.actualDuration !== null && d.actualDuration !== undefined
          ? statusBadge(d.actualDuration - d.plannedDuration)
          : null,
    },
    {
      label: '总成本',
      planned: `${fmtWanYuan(d.plannedCost)} 万`,
      actual: `${fmtWanYuan(d.actualCost)} 万`,
      diff: `${d.actualCost - d.plannedCost > 0 ? '+' : ''}${fmtWanYuan(d.actualCost - d.plannedCost)} 万`,
      badge: statusBadge(d.actualCost - d.plannedCost),
    },
    {
      label: '总碳排',
      planned: `${fmtNumber(d.plannedEmission / 1000, 2)} t`,
      actual: `${fmtNumber(d.actualEmission / 1000, 2)} t`,
      diff: `${d.actualEmission - d.plannedEmission > 0 ? '+' : ''}${fmtNumber((d.actualEmission - d.plannedEmission) / 1000, 2)} t`,
      badge: statusBadge(d.actualEmission - d.plannedEmission),
    },
  ]
})

function taskBadge(row: ComplianceTaskRow): { label: string; cls: string } {
  if (!row.isCompleted) return { label: '未完成', cls: 'badge-warning' }
  if (!row.plannedEndDate || !row.actualCompletionDate)
    return { label: '达标', cls: 'badge-success' }
  const diffMs =
    new Date(row.actualCompletionDate).getTime() - new Date(row.plannedEndDate).getTime()
  return statusBadge(diffMs)
}

const monthlyRows = computed(() => data.value?.monthly ?? [])
</script>

<template>
  <div class="h-full flex flex-col gap-4 overflow-y-auto">
    <!-- 状态徽标（原顶栏投送，移至页内工具条） -->
    <div v-if="data" class="flex items-center justify-end">
      <span
        class="text-xs font-mono px-2 py-1 rounded-full"
        :class="data.evaluationUnlocked ? 'bg-success/15 text-success' : 'bg-warning/15 text-warning'"
      >
        {{ data.evaluationUnlocked ? '评价已解锁' : '评价未解锁' }}
      </span>
    </div>
    <div
      v-if="plan?.isStale"
      class="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2.5"
    >
      <span class="material-symbols-outlined text-warning icon-sm mt-0.5">warning</span>
      <p class="text-xs text-base-content">
        计划基线数据已变更，当前对照基于旧基线。建议到「计划编制」重新预估并保存； 也可在「设置 →
        数据体检」中手动检查过期状态。
      </p>
    </div>

    <ChartEmptyState
      v-if="isNoPlan"
      icon="fact_check"
      title="尚未保存施工计划基线"
      description="请先到「计划编制」页保存为计划基线"
    />
    <div v-else-if="isLoading" class="space-y-4">
      <div class="grid grid-cols-3 gap-4">
        <div v-for="i in 3" :key="i" class="skeleton h-24 w-full rounded-lg"></div>
      </div>
      <div class="skeleton h-64 w-full rounded-lg"></div>
    </div>

    <template v-else-if="data">
      <div class="grid grid-cols-3 gap-4">
        <div v-for="c in cards" :key="c.label" class="panel p-4">
          <div class="flex items-center justify-between mb-2">
            <p class="text-xs text-fg-subtle">{{ c.label }}</p>
            <span v-if="c.badge" class="badge badge-sm" :class="c.badge.cls">
              {{ c.badge.label }}
            </span>
          </div>
          <div class="flex items-baseline justify-between gap-2">
            <div>
              <p class="text-[11px] text-fg-subtle">计划</p>
              <p class="text-sm font-semibold font-num text-base-content">{{ c.planned }}</p>
            </div>
            <div>
              <p class="text-[11px] text-fg-subtle">实际</p>
              <p class="text-sm font-semibold font-num text-base-content">{{ c.actual }}</p>
            </div>
            <span
              class="text-xs font-num"
              :class="
                !c.badge ? 'text-fg-subtle' : c.badge.cls === 'badge-success' ? 'text-success' : 'text-warning'
              "
            >
              {{ c.diff }}
            </span>
          </div>
        </div>
      </div>

      <div class="panel p-4">
        <h2 class="section-title">各工序完成时间</h2>
        <div class="overflow-x-auto">
          <table class="table table-sm">
            <thead>
              <tr>
                <th>工序</th>
                <th>计划开始</th>
                <th>计划完成</th>
                <th>实际开始</th>
                <th>实际完成</th>
                <th class="table-num">当前进度</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in data.taskRows" :key="row.taskId">
                <td class="font-medium">{{ row.code }} {{ row.name }}</td>
                <td class="font-num">{{ row.plannedStartDate ?? '—' }}</td>
                <td class="font-num">{{ row.plannedEndDate ?? '—' }}</td>
                <td class="font-num">{{ row.actualStartDate ?? '—' }}</td>
                <td class="font-num">{{ row.actualCompletionDate ?? '—' }}</td>
                <td class="table-num">{{ row.currentPercent }}%</td>
                <td>
                  <span class="badge badge-sm" :class="taskBadge(row).cls">
                    {{ taskBadge(row).label }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel p-4">
        <h2 class="section-title">材料用量差异</h2>
        <div v-if="data.materialDiffs.length === 0" class="py-4 text-center text-sm text-fg-muted">
          暂无差异数据
        </div>
        <div v-else class="overflow-x-auto">
          <table class="table table-sm">
            <thead>
              <tr>
                <th>资源</th>
                <th class="table-num">计划用量</th>
                <th class="table-num">实际用量</th>
                <th class="table-num">差异</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in data.materialDiffs" :key="m.resourceId">
                <td>{{ m.resourceName }}</td>
                <td class="table-num">{{ fmtNumber(m.plannedQuantity, 1) }}</td>
                <td class="table-num">{{ fmtNumber(m.actualQuantity, 1) }}</td>
                <td
                  class="table-num"
                  :class="
                    m.difference === 0
                      ? 'text-fg-subtle'
                      : m.difference > 0
                        ? 'text-warning'
                        : 'text-success'
                  "
                >
                  {{ m.difference > 0 ? '+' : '' }}{{ fmtNumber(m.difference, 1) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel p-4">
        <h2 class="section-title">每月成本 / 碳排对照</h2>
        <div v-if="monthlyRows.length === 0" class="py-4 text-center text-sm text-fg-muted">
          暂无月度数据
        </div>
        <div v-else class="overflow-x-auto">
          <table class="table table-sm">
            <thead>
              <tr>
                <th>月份</th>
                <th class="table-num">计划成本</th>
                <th class="table-num">实际成本</th>
                <th class="table-num">计划碳排</th>
                <th class="table-num">实际碳排</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in monthlyRows" :key="m.month">
                <td class="font-num">{{ m.month }}</td>
                <td class="table-num">{{ fmtWanYuan(m.plannedCost) }}</td>
                <td class="table-num">{{ fmtWanYuan(m.actualCost) }}</td>
                <td class="table-num">{{ fmtNumber(m.plannedEmission / 1000, 2) }} t</td>
                <td class="table-num">{{ fmtNumber(m.actualEmission / 1000, 2) }} t</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
