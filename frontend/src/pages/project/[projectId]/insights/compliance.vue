<script setup lang="ts">
import { computed } from 'vue'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import PageHead from '@/components/common/PageHead.vue'
import StatCard from '@/components/common/StatCard.vue'
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

interface DiffCard {
  label: string
  value: string
  unit?: string
  icon: string
  color: 'primary' | 'warning' | 'success'
  /** 计划 vs 实际附加说明 */
  sub: string
  trend?: { direction: 'up' | 'down'; text: string }
}

const cards = computed<DiffCard[]>(() => {
  const d = data.value
  if (!d) return []

  const durationDiff =
    d.actualDuration !== null && d.actualDuration !== undefined
      ? d.actualDuration - d.plannedDuration
      : null
  const costDiff = d.actualCost - d.plannedCost
  const emissionDiff = d.actualEmission - d.plannedEmission

  return [
    {
      label: '工期差异',
      value: durationDiff !== null ? `${durationDiff > 0 ? '+' : ''}${fmtNumber(durationDiff, 1)}` : '—',
      unit: durationDiff !== null ? '天' : undefined,
      icon: 'schedule',
      color: 'primary',
      sub:
        durationDiff !== null
          ? `计划 ${fmtNumber(d.plannedDuration, 1)} 天 · 实际 ${fmtNumber(d.actualDuration!, 1)} 天`
          : `计划 ${fmtNumber(d.plannedDuration, 1)} 天`,
      trend:
        durationDiff === null
          ? undefined
          : durationDiff > 0
            ? { direction: 'down', text: '延期，需关注' }
            : { direction: 'up', text: '可控' },
    },
    {
      label: '成本差异',
      value: `${costDiff > 0 ? '+' : ''}${fmtWanYuan(costDiff)}`,
      unit: '万元',
      icon: 'payments',
      color: 'warning',
      sub: `计划 ${fmtWanYuan(d.plannedCost)} 万 · 实际 ${fmtWanYuan(d.actualCost)} 万`,
      trend: costDiff > 0 ? { direction: 'down', text: '超支' } : { direction: 'up', text: '节约' },
    },
    {
      label: '碳排差异',
      value: `${emissionDiff > 0 ? '+' : ''}${fmtNumber(emissionDiff / 1000, 2)}`,
      unit: 't',
      icon: 'eco',
      color: 'success',
      sub: `计划 ${fmtNumber(d.plannedEmission / 1000, 2)} t · 实际 ${fmtNumber(d.actualEmission / 1000, 2)} t`,
      trend:
        emissionDiff > 0 ? { direction: 'down', text: '超排' } : { direction: 'up', text: '减排' },
    },
  ]
})

/** 达标评价：三项差异均 <= 0 视为达标 */
const evaluation = computed<{ label: string; ok: boolean } | null>(() => {
  const d = data.value
  if (!d) return null
  const durationDiff =
    d.actualDuration !== null && d.actualDuration !== undefined
      ? d.actualDuration - d.plannedDuration
      : 0
  const ok = durationDiff <= 0 && d.actualCost - d.plannedCost <= 0 && d.actualEmission - d.plannedEmission <= 0
  return { label: ok ? '达标' : '需关注', ok }
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
    <PageHead title="计划践行度" subtitle="计划基线与实际执行的差异对照与达标评价">
      <span v-if="plan?.isStale" class="badge badge-warning">基线已过期，建议重新预估</span>
    </PageHead>

    <ChartEmptyState
      v-if="isNoPlan"
      icon="fact_check"
      title="尚未保存施工计划基线"
    />
    <div v-else-if="isLoading" class="space-y-4">
      <div class="stat-row">
        <div v-for="i in 4" :key="i" class="skeleton h-24 w-full rounded-lg"></div>
      </div>
      <div class="skeleton h-64 w-full rounded-lg"></div>
    </div>

    <template v-else-if="data">
      <!-- 差异统计卡 + 达标评价（设计稿 stat-row + trend） -->
      <div class="stat-row">
        <StatCard
          v-for="c in cards"
          :key="c.label"
          :label="c.label"
          :value="c.value"
          :unit="c.unit"
          :icon="c.icon"
          :color="c.color"
          :trend="c.trend"
        >
          {{ c.sub }}
        </StatCard>
        <StatCard
          v-if="evaluation"
          label="评价"
          :value="evaluation.label"
          :icon="evaluation.ok ? 'fact_check' : 'warning'"
          :color="evaluation.ok ? 'success' : 'warning'"
        />
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
