<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery, useQueryCache } from '@pinia/colada'
import LoadingState from '@/components/common/LoadingState.vue'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import StatCard from '@/components/common/StatCard.vue'
import { useProjectContext } from '@/composables/useProjectContext'
import { useDiagnosticsApi, type DiagnosticsUsageType } from '@/composables/useDiagnosticsApi'
import { planStaleDiagnosticsQuery, planStaleDiagnosticsQueryKey } from '@/client/@pinia/colada.gen'
import { categoryConfigMap } from '@/types/resource'
import { fmtNumber } from '@/utils/format'
import type { DiagnosticFlag, ResourceDiagnosticItem } from '@/client/types.gen'

definePage({
  meta: {
    title: '数据体检',
    description: '检查有使用记录的资源是否存在异常口径（零碳因子 / 零单价等）',
    icon: 'health_and_safety',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 9,
  },
})

// ──── 用量口径切换 ─────────────────────────────────────────
const usageType = ref<DiagnosticsUsageType>('ALL')
const usageTypeOptions: ReadonlyArray<SegmentOption<DiagnosticsUsageType>> = [
  { value: 'ALL', label: '全部', icon: 'select_all' },
  { value: 'ACTUAL', label: '实际', icon: 'fact_check' },
  { value: 'PLANNED', label: '计划', icon: 'edit_note' },
]

const { items, isLoading, zeroFactorCount, infoCount, refresh } = useDiagnosticsApi(
  () => usageType.value,
)

/** 检查的资源总数 */
const checkedCount = computed(() => items.value.length)

// ──── 计划基线过期检查（手动触发：仅本页检查时更新，不监听业务变更） ──
const queryCache = useQueryCache()
const { currentProjectId } = useProjectContext()
const planQuery = useQuery(() => ({
  ...planStaleDiagnosticsQuery({
    path: { project_id: currentProjectId.value! },
  }),
  enabled: !!currentProjectId.value,
}))
const planCheck = computed(() => planQuery.state.value?.data ?? null)
const isLoadingPlan = computed(() => planQuery.asyncStatus.value === 'loading')

async function recheckPlan() {
  await queryCache.invalidateQueries({
    key: planStaleDiagnosticsQueryKey({
      path: { project_id: currentProjectId.value! },
    }),
  })
}

// ──── 分组：warning（零因子）与 info ───────────────────────
const zeroFactorItems = computed(() =>
  items.value.filter((it) => it.flags?.includes('ZERO_FACTOR')),
)
const infoItems = computed(() =>
  items.value.filter((it) => {
    const flags = it.flags ?? []
    return flags.length > 0 && !flags.includes('ZERO_FACTOR')
  }),
)

function categoryLabel(item: ResourceDiagnosticItem): string {
  return categoryConfigMap[item.category]?.label ?? item.category
}

const flagMeta: Record<DiagnosticFlag, { label: string; cls: string }> = {
  ZERO_FACTOR: { label: '零碳因子', cls: 'bg-warning/15 text-warning' },
  NEGATIVE_FACTOR: { label: '负因子 · 碳汇', cls: 'bg-success/15 text-success' },
  ZERO_PRICE: { label: '零单价', cls: 'bg-info/15 text-info' },
}
</script>

<template>
  <div class="h-full flex flex-col gap-4 overflow-y-auto">
    <!-- 头部 -->
    <div class="flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-lg font-semibold text-base-content">数据体检</h1>
        <p class="text-xs text-fg-subtle mt-0.5">
          只读检查，不影响任何功能。碳排放计算边界由你决定：若资源仅为 峰值人数 /
          资源约束而记录用量，零碳因子属正常情况，可忽略。
        </p>
      </div>
      <SegmentControl v-model="usageType" :options="usageTypeOptions" aria-label="用量口径" />
    </div>

    <LoadingState v-if="isLoading" variant="skeleton" />

    <template v-else>
      <!-- 概览 -->
      <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
        <StatCard
          label="检查资源数"
          :value="fmtNumber(checkedCount, 0)"
          unit="种"
          icon="inventory"
          color="neutral"
        />
        <StatCard
          label="需注意（零碳因子）"
          :value="fmtNumber(zeroFactorCount, 0)"
          unit="种"
          icon="eco"
          color="warning"
        />
        <StatCard
          label="提示项"
          :value="fmtNumber(infoCount, 0)"
          unit="种"
          icon="info"
          color="info"
        />
      </div>

      <!-- 计划基线过期检查 -->
      <section class="panel p-4">
        <div class="flex items-center justify-between gap-4 mb-1">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-base-content icon-sm">fact_check</span>
            <h2 class="text-sm font-semibold text-base-content">计划基线过期检查</h2>
          </div>
          <button class="btn btn-ghost btn-xs" :disabled="isLoadingPlan" @click="recheckPlan">
            <span v-if="isLoadingPlan" class="loading loading-spinner loading-xs"></span>
            <span v-else class="material-symbols-outlined icon-sm">refresh</span>
            重新检查
          </button>
        </div>
        <p class="text-xs text-fg-subtle mb-3">
          对比「计划编制」保存基线时的任务/依赖/计划用量/资源/周转/措施等输入与当前数据。
          仅在本页点击检查时更新，不监听业务变更。
        </p>
        <div v-if="isLoadingPlan && !planCheck" class="skeleton h-8 w-full rounded-lg"></div>
        <div v-else-if="!planCheck" class="text-xs text-fg-subtle">
          暂无检查结果，点击「重新检查」获取。
        </div>
        <div v-else-if="!planCheck.hasPlan" class="flex items-center gap-2 text-xs text-fg-subtle">
          <span class="material-symbols-outlined icon-sm">info</span>
          尚未保存施工计划基线，请先到「分析洞察 → 计划编制」保存基线。
        </div>
        <div v-else class="flex items-center gap-3 flex-wrap">
          <span
            class="text-xs font-medium px-2 py-0.5 rounded-full"
            :class="planCheck.isStale ? 'bg-warning/15 text-warning' : 'bg-success/15 text-success'"
          >
            {{ planCheck.isStale ? '基线已过期' : '基线最新' }}
          </span>
          <span class="text-xs text-fg-subtle">
            {{
              planCheck.isStale
                ? '任务/依赖/计划用量/资源/周转/措施等已变化，建议到「计划编制」重新预估并保存基线。'
                : '基线输入与当前数据一致，无需重新保存。'
            }}
          </span>
          <span v-if="planCheck.checkedAt" class="text-[11px] text-fg-muted font-mono ml-auto">
            检查于 {{ new Date(planCheck.checkedAt).toLocaleString() }}
          </span>
        </div>
      </section>

      <!-- 无任何提示 -->
      <ChartEmptyState
        v-if="checkedCount === 0"
        icon="task_alt"
        title="暂无有使用记录的资源"
        description="录入日报或资源使用后，这里会自动出现体检结果。"
      />
      <template v-else-if="zeroFactorItems.length === 0 && infoItems.length === 0">
        <ChartEmptyState
          icon="verified"
          title="一切正常"
          description="所有有使用记录的资源均已设置碳排放因子与单价。"
        />
      </template>

      <!-- warning：零碳因子 -->
      <section v-if="zeroFactorItems.length > 0" class="panel p-4">
        <div class="flex items-center gap-2 mb-1">
          <span class="material-symbols-outlined text-warning icon-sm">warning</span>
          <h2 class="text-sm font-semibold text-base-content">
            零碳因子资源（{{ zeroFactorItems.length }}）
          </h2>
        </div>
        <p class="text-xs text-fg-subtle mb-3">
          以下资源存在使用记录但碳排放因子为 0——其用量<b>不会计入任何碳排结果</b>。
          若这符合项目的计算边界（如工种仅用于统计峰值人数、资源约束），可忽略；
          否则请到「资源管理」补填碳排放因子。
        </p>
        <table class="table">
          <thead>
            <tr>
              <th>资源名称</th>
              <th class="w-20">类别</th>
              <th class="w-16">单位</th>
              <th class="w-28 table-num">实际用量</th>
              <th class="w-28 table-num">计划用量</th>
              <th class="w-24">最近使用</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in zeroFactorItems" :key="item.resourceId">
              <td>
                <span class="font-medium">{{ item.name }}</span>
                <span
                  class="ml-2 text-[11px] px-1.5 py-0.5 rounded-full"
                  :class="flagMeta.ZERO_FACTOR.cls"
                >
                  {{ flagMeta.ZERO_FACTOR.label }}
                </span>
              </td>
              <td>{{ categoryLabel(item) }}</td>
              <td>{{ item.unit }}</td>
              <td class="table-num">{{ fmtNumber(item.actualQuantity ?? 0, 1) }}</td>
              <td class="table-num">{{ fmtNumber(item.plannedQuantity ?? 0, 1) }}</td>
              <td>{{ item.lastUsageDate ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- info：负因子 / 零单价 -->
      <section v-if="infoItems.length > 0" class="panel p-4">
        <div class="flex items-center gap-2 mb-1">
          <span class="material-symbols-outlined text-info icon-sm">info</span>
          <h2 class="text-sm font-semibold text-base-content">提示项（{{ infoItems.length }}）</h2>
        </div>
        <p class="text-xs text-fg-subtle mb-3">
          负因子 = 碳汇资源（如光伏发电，「低碳措施」的添加类措施依赖它）；零单价 =
          用量不计成本。确认符合预期即可忽略。
        </p>
        <table class="table">
          <thead>
            <tr>
              <th>资源名称</th>
              <th class="w-20">类别</th>
              <th class="w-16">单位</th>
              <th class="w-32 table-num">单价（元）</th>
              <th class="w-36 table-num">碳因子（kg）</th>
              <th class="w-28 table-num">实际用量</th>
              <th class="w-28 table-num">计划用量</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in infoItems" :key="item.resourceId">
              <td>
                <span
                  v-for="flag in item.flags"
                  :key="flag"
                  class="mr-2 text-[11px] px-1.5 py-0.5 rounded-full"
                  :class="flagMeta[flag].cls"
                >
                  {{ flagMeta[flag].label }}
                </span>
                <span class="font-medium">{{ item.name }}</span>
              </td>
              <td>{{ categoryLabel(item) }}</td>
              <td>{{ item.unit }}</td>
              <td class="table-num">{{ fmtNumber(item.unitPrice, 2) }}</td>
              <td class="table-num">{{ fmtNumber(item.carbonFactor, 2) }}</td>
              <td class="table-num">{{ fmtNumber(item.actualQuantity ?? 0, 1) }}</td>
              <td class="table-num">{{ fmtNumber(item.plannedQuantity ?? 0, 1) }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </div>
</template>
