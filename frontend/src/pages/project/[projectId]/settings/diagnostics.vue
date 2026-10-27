<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery, useQueryCache } from '@pinia/colada'
import LoadingState from '@/components/common/LoadingState.vue'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import StatCard from '@/components/common/StatCard.vue'
import { useProjectContext } from '@/composables/useProjectContext'
import {
  useDiagnosticsApi,
  useTagChartDiagnostics,
  type DiagnosticsUsageType,
} from '@/composables/useDiagnosticsApi'
import { useSnapshotManualRefresh, useSnapshotRefreshInfo } from '@/composables/useSnapshotApi'
import { planStaleDiagnosticsQuery, planStaleDiagnosticsQueryKey } from '@/client/@pinia/colada.gen'
import { categoryConfigMap } from '@/types/resource'
import { fmtNumber } from '@/utils/format'
import type { DiagnosticFlag, ResourceDiagnosticItem } from '@/client/types.gen'
import { useToast } from '@/composables/useToast'

definePage({
  meta: {
    title: '数据体检',
    description: '只读检查：资源口径异常 / 标签切片重叠 / 计划基线过期 / 数据新鲜度',
    icon: 'health_and_safety',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 9,
  },
})

const { notifySuccess, notifyError } = useToast()

// ──── 用量口径切换 ─────────────────────────────────────────
const usageType = ref<DiagnosticsUsageType>('ALL')
const usageTypeOptions: ReadonlyArray<SegmentOption<DiagnosticsUsageType>> = [
  { value: 'ALL', label: '全部', icon: 'select_all' },
  { value: 'ACTUAL', label: '实际', icon: 'fact_check' },
  { value: 'PLANNED', label: '计划', icon: 'edit_note' },
]

const { items, isLoading, zeroFactorCount, refresh } = useDiagnosticsApi(
  () => usageType.value,
)

/** 检查的资源总数 */
const checkedCount = computed(() => items.value.length)

/** 零单价资源数（设计稿概览卡） */
const zeroPriceCount = computed(
  () => items.value.filter((it) => it.flags?.includes('ZERO_PRICE')).length,
)

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

/** 零单价（且非零因子）资源 */
const zeroPriceItems = computed(() =>
  items.value.filter(
    (it) => it.flags?.includes('ZERO_PRICE') && !it.flags?.includes('ZERO_FACTOR'),
  ),
)

/** 负因子（碳汇，且非零因子）资源 */
const negativeFactorItems = computed(() =>
  items.value.filter(
    (it) => it.flags?.includes('NEGATIVE_FACTOR') && !it.flags?.includes('ZERO_FACTOR'),
  ),
)

/** 提示项摘要：名称列表（设计稿 alert 描述），过长时截断 */
function namesOf(list: ResourceDiagnosticItem[], max = 6): string {
  const names = list.map((it) => it.name)
  if (names.length <= max) return names.join('、')
  return `${names.slice(0, max).join('、')} 等 ${names.length} 个`
}

const infoItems = computed(() =>
  items.value.filter((it) => {
    const flags = it.flags ?? []
    return flags.length > 0 && !flags.includes('ZERO_FACTOR')
  }),
)

// ──── 标签/切片重叠体检 ────────────────────────────────────
const {
  items: tagChartItems,
  isLoading: isTagChartLoading,
  refresh: refreshTagChart,
} = useTagChartDiagnostics()

// ──── 物化视图新鲜度 + 手动刷新 ───────────────────────────
const { info: snapshotInfo, refresh: refreshSnapshotInfo } = useSnapshotRefreshInfo()
const { refreshSnapshot, isRefreshing } = useSnapshotManualRefresh()

// ──── 全局重新检查（设计稿 toolbar「重新检查」：汇总所有只读检查） ──
const isRechecking = computed(
  () => isLoadingPlan.value || isTagChartLoading.value || isRefreshing.value,
)

async function recheckAll() {
  await Promise.allSettled([refresh(), recheckPlan(), refreshTagChart(), refreshSnapshotInfo()])
}

async function handleManualRefresh() {
  try {
    await refreshSnapshot({ path: { project_id: currentProjectId.value! } })
    await refreshSnapshotInfo()
    notifySuccess('数据已刷新')
  } catch (e) {
    console.error('Manual snapshot refresh failed:', e)
    notifyError({ title: '刷新失败', description: String(e) })
  }
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

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
    <!-- 用量口径切换 -->
    <div class="flex items-center justify-end">
      <SegmentControl v-model="usageType" :options="usageTypeOptions" aria-label="用量口径" />
    </div>

    <LoadingState v-if="isLoading" variant="skeleton" />

    <template v-else>
      <!-- 概览（设计稿 4 统计卡：检查总数 / 零碳因子 / 零单价 / 计划基线） -->
      <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="检查资源总数"
          :value="fmtNumber(checkedCount, 0)"
          unit="种"
          icon="fact_check"
          color="success"
        />
        <StatCard
          label="零碳因子资源"
          :value="fmtNumber(zeroFactorCount, 0)"
          unit="种"
          icon="warning"
          color="warning"
        />
        <StatCard
          label="零单价资源"
          :value="fmtNumber(zeroPriceCount, 0)"
          unit="种"
          icon="payments"
          color="warning"
        />
        <StatCard
          label="计划基线"
          :value="!planCheck ? '—' : !planCheck.hasPlan ? '未保存' : planCheck.isStale ? '已过期' : '正常'"
          icon="schedule"
          :color="!planCheck || !planCheck.hasPlan ? 'neutral' : planCheck.isStale ? 'error' : 'success'"
        />
      </div>

      <!-- 提示项（设计稿：单卡片 alert 列表） -->
      <section class="panel p-0">
        <div class="card-head">
          <h2 class="section-title m-0">提示项</h2>
          <button class="btn btn-ghost btn-sm" :disabled="isRechecking" @click="recheckAll">
            <span v-if="isRechecking" class="loading loading-spinner loading-xs" />
            <span v-else class="material-symbols-outlined icon-sm">refresh</span>
            重新检查
          </button>
        </div>
        <div class="card-body flex flex-col gap-2.5">
          <!-- 无使用记录资源 -->
          <div v-if="checkedCount === 0" class="alert alert-soft">
            <span class="material-symbols-outlined icon-md shrink-0 text-fg-muted">info</span>
            <div class="min-w-0">
              <p class="font-semibold text-sm text-base-content">暂无有使用记录的资源</p>
              <p class="text-xs text-fg-muted mt-0.5">
                录入日报或资源使用后，这里会自动出现体检结果。
              </p>
            </div>
          </div>

          <template v-else>
            <!-- 零碳因子 -->
            <div v-if="zeroFactorItems.length > 0" class="alert alert-warning">
              <span class="material-symbols-outlined icon-md shrink-0">warning</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">
                  {{ zeroFactorItems.length }} 个资源存在使用记录但碳排放因子为 0
                </p>
                <p class="text-xs text-fg-muted mt-0.5">
                  {{ namesOf(zeroFactorItems) }} ——
                  其用量不会计入任何碳排结果，请到资源管理补填。
                </p>
              </div>
              <RouterLink
                class="btn btn-ghost btn-sm ml-auto shrink-0"
                :to="{
                  name: '/project/[projectId]/settings/resources',
                  params: { projectId: currentProjectId ?? 0 },
                }"
              >
                去补填
              </RouterLink>
            </div>
            <div v-else class="alert alert-success">
              <span class="material-symbols-outlined icon-md shrink-0">check_circle</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">碳排放因子检查通过</p>
                <p class="text-xs text-fg-muted mt-0.5">
                  所有有使用记录的资源均已设置碳排放因子。
                </p>
              </div>
            </div>

            <!-- 零单价 -->
            <div v-if="zeroPriceItems.length > 0" class="alert alert-warning">
              <span class="material-symbols-outlined icon-md shrink-0">payments</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">
                  {{ zeroPriceItems.length }} 个资源单价为 0
                </p>
                <p class="text-xs text-fg-muted mt-0.5">
                  {{ namesOf(zeroPriceItems) }} —— 用量不计成本，如符合预期可忽略。
                </p>
              </div>
            </div>

            <!-- 碳汇（负因子） -->
            <div v-if="negativeFactorItems.length > 0" class="alert alert-success">
              <span class="material-symbols-outlined icon-md shrink-0">eco</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">
                  {{ negativeFactorItems.length }} 个碳汇资源（负因子）
                </p>
                <p class="text-xs text-fg-muted mt-0.5">
                  {{ namesOf(negativeFactorItems) }} ——
                  「低碳措施」的添加类措施依赖碳汇资源抵扣碳排放。
                </p>
              </div>
            </div>

            <!-- 计划基线 -->
            <div v-if="isLoadingPlan && !planCheck" class="skeleton h-9 w-full rounded-lg" />
            <div v-else-if="!planCheck" class="alert alert-soft">
              <span class="material-symbols-outlined icon-md shrink-0 text-fg-muted">info</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">基线检查暂不可用</p>
                <p class="text-xs text-fg-muted mt-0.5">点击「重新检查」重试。</p>
              </div>
            </div>
            <div v-else-if="!planCheck.hasPlan" class="alert alert-warning">
              <span class="material-symbols-outlined icon-md shrink-0">schedule</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">尚未保存施工计划基线</p>
                <p class="text-xs text-fg-muted mt-0.5">
                  请先到「分析洞察 → 计划编制」预估并保存基线。
                </p>
              </div>
              <RouterLink
                class="btn btn-ghost btn-sm ml-auto shrink-0"
                :to="{
                  name: '/project/[projectId]/insights/planning',
                  params: { projectId: currentProjectId ?? 0 },
                }"
              >
                前往
              </RouterLink>
            </div>
            <div v-else-if="planCheck.isStale" class="alert alert-warning">
              <span class="material-symbols-outlined icon-md shrink-0">schedule</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">计划基线已过期</p>
                <p class="text-xs text-fg-muted mt-0.5">
                  任务/依赖/计划用量/资源/周转/措施等已变化，建议到「计划编制」重新预估并保存基线。
                </p>
              </div>
              <RouterLink
                class="btn btn-ghost btn-sm ml-auto shrink-0"
                :to="{
                  name: '/project/[projectId]/insights/planning',
                  params: { projectId: currentProjectId ?? 0 },
                }"
              >
                前往
              </RouterLink>
            </div>
            <div v-else class="alert alert-success">
              <span class="material-symbols-outlined icon-md shrink-0">check_circle</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">计划基线最新</p>
                <p class="text-xs text-fg-muted mt-0.5">
                  基线输入与当前数据一致，无需重新保存。
                </p>
              </div>
            </div>

            <!-- 标签 / 切片重叠 -->
            <div
              v-if="!isTagChartLoading && tagChartItems.length === 0"
              class="alert alert-success"
            >
              <span class="material-symbols-outlined icon-md shrink-0">check_circle</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">切片标签无重叠</p>
                <p class="text-xs text-fg-muted mt-0.5">
                  未发现同一图表内切片标签重叠导致重复计入。
                </p>
              </div>
            </div>
            <template v-else>
              <div v-for="(item, i) in tagChartItems" :key="i" class="alert alert-warning">
                <span class="material-symbols-outlined icon-md shrink-0">warning</span>
                <div class="min-w-0">
                  <p class="font-semibold text-sm text-base-content">
                    图表「{{ item.chartName }}」切片标签重叠
                  </p>
                  <p class="text-xs text-fg-muted mt-0.5">
                    切片：{{ item.sliceNames?.join('、') }} —— {{ item.detail }}
                  </p>
                </div>
              </div>
            </template>

            <!-- 数据新鲜度 -->
            <div class="alert alert-info">
              <span class="material-symbols-outlined icon-md shrink-0">database</span>
              <div class="min-w-0">
                <p class="font-semibold text-sm text-base-content">碳排放数据源新鲜度</p>
                <p class="text-xs text-fg-muted mt-0.5">
                  上次刷新 {{ fmtTime(snapshotInfo?.lastRefreshedAt) }} · 下次计划刷新
                  {{ fmtTime(snapshotInfo?.nextRefreshDue) }}
                </p>
              </div>
              <button
                class="btn btn-ghost btn-sm ml-auto shrink-0"
                :disabled="isRefreshing"
                @click="handleManualRefresh"
              >
                <span v-if="isRefreshing" class="loading loading-spinner loading-xs" />
                立即刷新
              </button>
            </div>
          </template>
        </div>
      </section>

      <!-- warning：零碳因子（明细） -->
      <section v-if="zeroFactorItems.length > 0" class="panel p-0">
        <div class="card-head">
          <h2 class="section-title m-0">零碳因子资源明细（{{ zeroFactorItems.length }}）</h2>
        </div>
        <div class="card-body">
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
        </div>
      </section>

      <!-- info：负因子 / 零单价（明细） -->
      <section v-if="infoItems.length > 0" class="panel p-0">
        <div class="card-head">
          <h2 class="section-title m-0">提示项明细（{{ infoItems.length }}）</h2>
        </div>
        <div class="card-body">
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
        </div>
      </section>
    </template>
  </div>
</template>
