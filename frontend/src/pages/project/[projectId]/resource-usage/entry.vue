<script setup lang="ts">
/**
 * 资源使用量 - 录入（手动/日报统一入口）
 *
 * - 顶部工具栏：使用日期 + 口径徽标 + 从日报导入（仅实际口径可用）
 * - 统一「活动数据列表」（UsageEntrySummary）：已保存记录 ∪ 待提交日报批次；
 *   导入 / 新增 / 编辑 / 删除 立即写入后端
 * - 当日工序进度（可选）+ 一键「计算」（提交待提交日报批次并刷新统计）
 *
 * 「碳排放计算结果」三个统计卡与列表列口径一致：
 * - 计划碳排 = 计划活动数据列表「碳排放量」列之和（当日已保存计划记录）
 * - 进度碳排 = 实际活动数据列表「碳排放量」列之和（当日已保存实际记录
 *   + 待提交日报批次条目）
 * - 碳排放指标 = 项目信息「施工阶段碳排放总量指标」
 * 碳排放量 = 用量 × 碳排放因子 / 1000。
 */
import { computed, ref, watch } from 'vue'
import { useQuery, useQueryCache } from '@pinia/colada'
import UsageEntrySummary from '@/components/resource-usage/UsageEntrySummary.vue'
import PageHead from '@/components/common/PageHead.vue'
import { useResourceUsagesByDate } from '@/composables/useResourceUsageApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useUsageDateType } from '@/composables/useUsageDateType'
import { useDailyReportStoreV2 } from '@/stores/report'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useToast } from '@/composables/useToast'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { listResourcesQuery, listResourceUsagesQueryKey } from '@/client/@pinia/colada.gen'
import type { UsageType } from '@/client/types.gen'
import { ApiError, formatHttpError } from '@/utils/error'

import StatCard from '@/components/common/StatCard.vue'
import { useProjectApi } from '@/composables/useProjectApi'

definePage({
  meta: {
    title: '录入',
    description: '手动/日报统一录入入口',
    icon: 'edit_note',
    showInNav: false,
    parentName: '/project/[projectId]/resource-usage',
    navOrder: 2,
  },
})

/**
 * 固定口径（计划/实际数据录入两个菜单入口共用本页）：
 * - null（直接访问本路由）→ 保持原行为：按日期自动推断 + 可强制切换
 * - 'PLANNED' / 'ACTUAL' → 入口页固定口径，隐藏强制切换
 */
const { pinnedType = null } = defineProps<{
  pinnedType?: 'PLANNED' | 'ACTUAL' | null
}>()

const { currentProjectId } = useProjectContext()

// 共享日期 + 用量类型推断（手动与日报共用）
const { usageDate, effectiveUsageType: inferredType } = useUsageDateType()

// 生效口径：入口固定时优先生效，否则用推断结果
const effectiveUsageType = computed(() => pinnedType ?? inferredType.value)

// 提交结果错误信息
const submitErrorMessage = ref('')
const submitting = ref(false)

// ─── 列表数据源：当日 + 生效口径的已保存记录（组件内导入/增删改后自动刷新） ──
const { records: existingRecords, refresh: refreshExisting } = useResourceUsagesByDate(
  usageDate,
  effectiveUsageType,
)

// 当用户切换日期时，重新拉取当日已有记录
watch(usageDate, () => {
  refreshExisting()
})

// ─── 日报批次（待提交） ────────────────────────────────────
const reportStore = useDailyReportStoreV2()
const hasPendingReportBatch = computed(
  () => !!reportStore.batchId && reportStore.resourceUsages.length > 0,
)

// ─── 左侧工序侧栏（设计稿：工序列表 + 当日记录计数） ──────────
const { tasks: scheduleTasks } = useScheduleApi()
const selectedTaskId = ref<number | null>(null)

/** 每个工序当日已有记录数（含待提交日报条目），用于侧栏计数徽标 */
const taskDayCounts = computed<Record<number, number>>(() => {
  const counts: Record<number, number> = {}
  for (const r of existingRecords.value) {
    counts[r.taskId] = (counts[r.taskId] ?? 0) + 1
  }
  for (const u of reportStore.resourceUsages) {
    counts[u.taskId] = (counts[u.taskId] ?? 0) + 1
  }
  return counts
})

const totalDayCount = computed(() => Object.values(taskDayCounts.value).reduce((s, n) => s + n, 0))

// ─── 碳排放计算结果（与列表「碳排放量」列同口径求和） ─────────
const { project } = useProjectApi()

/** 资源因子映射（碳排放量 = 用量 × 因子 / 1000） */
const { state: statResourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: FETCH_ALL_PAGE_SIZE },
  }),
)
const factorById = computed(() => {
  const m = new Map<number, number>()
  for (const r of statResourcesState.value?.data?.items ?? []) m.set(r.id, r.carbonFactor)
  return m
})
const factorByName = computed(() => {
  const m = new Map<string, number>()
  for (const r of statResourcesState.value?.data?.items ?? []) {
    m.set(r.name, r.carbonFactor)
    m.set(r.name.trim(), r.carbonFactor)
  }
  return m
})

/** 当日指定口径的已保存记录碳排放量之和（t） */
function useDayEmission(usageType: UsageType) {
  const { records } = useResourceUsagesByDate(usageDate, ref<UsageType>(usageType))
  return computed(
    () =>
      records.value.reduce((s, r) => s + r.quantity * (factorById.value.get(r.resourceId) ?? 0), 0) /
      1000,
  )
}

/** 计划碳排 = 计划活动数据列表「碳排放量」列之和（当日已保存计划记录） */
const plannedEmissionT = useDayEmission('PLANNED')
/** 进度碳排 = 实际活动数据列表「碳排放量」列之和（当日已保存实际记录 + 待提交日报批次） */
const actualSavedEmissionT = useDayEmission('ACTUAL')
const pendingDailyEmissionT = computed(
  () =>
    Array.from(reportStore.allocatedResourceQuantities.entries()).reduce(
      (sum, [, resourceQuantities]) =>
        sum +
        Object.entries(resourceQuantities).reduce(
          (s, [name, qty]) => s + qty * (factorByName.value.get(name) ?? 0),
          0,
        ),
      0,
    ) / 1000,
)
const actualEmissionT = computed(() => actualSavedEmissionT.value + pendingDailyEmissionT.value)
/** 碳排放指标 = 项目信息「施工阶段碳排放总量指标」 */
const emissionLimitT = computed(() => project.value?.construction_carbon_emission_limit ?? null)

/** 统计卡数值格式化（千分位 + 1 位小数） */
function fmtNum(v: number): string {
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}

// ─── 统一提交：计算（提交待提交日报批次并刷新统计） ─────────
const { notifySuccess, notifyError } = useToast()
const queryCache = useQueryCache()

async function handleCompleteDay() {
  // 按钮保持可点击：提交中重复点击直接忽略（不通过禁用表达）
  if (submitting.value) return
  submitErrorMessage.value = ''
  if (!hasPendingReportBatch.value) {
    notifyError({ title: '没有可提交的内容', description: '请先导入日报补充待提交批次' })
    return
  }

  submitting.value = true
  try {
    await reportStore.submitReport()
    notifySuccess({ title: '计算完成', description: '已提交日报 1 批' })
    reportStore.reset()
    // 日报落库后刷新列表/统计缓存
    await queryCache.invalidateQueries({
      key: listResourceUsagesQueryKey({
        path: { project_id: currentProjectId.value! },
      }),
    })
  } catch (e) {
    const err = e as ApiError
    submitErrorMessage.value =
      err?.status === 409
        ? `日报提交失败：${formatHttpError(err, '与现有记录冲突')}`
        : `日报提交失败：${formatHttpError(err, '未知错误')}`
    notifyError({ title: '提交失败', description: submitErrorMessage.value })
  } finally {
    submitting.value = false
  }
}

// ─── PageHead：按固定口径区分计划/实际录入页标题 ─────────────
const pageTitle = computed(() => {
  if (pinnedType === 'PLANNED') return '计划数据录入'
  if (pinnedType === 'ACTUAL') return '实际数据录入'
  return effectiveUsageType.value === 'ACTUAL' ? '实际数据录入' : '计划数据录入'
})
const pageSubtitle = computed(() => {
  if (pinnedType === 'PLANNED') return '按施工工序录入计划资源使用量'
  if (pinnedType === 'ACTUAL') return '按施工工序录入实际资源使用量'
  return effectiveUsageType.value === 'ACTUAL'
    ? '按施工工序录入实际资源使用量'
    : '按施工工序录入计划资源使用量'
})
</script>

<template>
  <PageHead :title="pageTitle" :subtitle="pageSubtitle" />

  <!-- 设计稿布局：左侧工序侧栏 + 右侧录入区（左右卡片顶/底对齐，最小高度同设计稿） -->
  <div class="grid grid-cols-1 lg:grid-cols-[230px_1fr] gap-4 items-stretch lg:min-h-[calc(100vh-190px)]">
    <!-- 左：施工工序（process-item 列表 + 当日计数） -->
    <aside class="panel p-0 h-full">
      <div class="px-4 py-3 border-b border-base-content/10">
        <h3 class="section-title m-0">施工工序</h3>
      </div>
      <div class="p-2 flex flex-col gap-0.5">
        <button
          type="button"
          class="process-item"
          :class="{ active: selectedTaskId === null }"
          @click="selectedTaskId = null"
        >
          <span>项目（全部）</span>
          <span class="pc">{{ totalDayCount }}</span>
        </button>
        <button
          v-for="t in scheduleTasks"
          :key="t.id"
          type="button"
          class="process-item sub"
          :class="{ active: selectedTaskId === t.id }"
          @click="selectedTaskId = selectedTaskId === t.id ? null : t.id"
        >
          <span class="truncate">{{ t.name }}</span>
          <span class="pc">{{ taskDayCounts[t.id] ?? 0 }}</span>
        </button>
        <p v-if="scheduleTasks.length === 0" class="text-xs text-fg-subtle px-3 py-2">
          暂无工序，请先到「施工工序管理」添加
        </p>
      </div>
    </aside>

    <!-- 右：录入内容（纵向 flex，计算按钮固定在列底部，与左侧工序卡底对齐） -->
    <div class="min-w-0 flex flex-col">
  <!-- 活动数据列表卡片（设计稿：模板下载/导入/新增/批量删除 + 阶段 tab + 日期 + 表格 + 分页；
       卡片拉伸占满剩余高度，计算结果与计算按钮固定在底部） -->
  <UsageEntrySummary
    v-model:usage-date="usageDate"
    class="flex-1 min-h-0"
    :usage-type="effectiveUsageType"
    :records="existingRecords"
    :selected-task-id="selectedTaskId"
  />

  <!-- 碳排放计算结果（设计稿底部统计卡） -->
  <div class="panel p-4 mt-4">
    <h3 class="section-title">碳排放计算结果</h3>
    <div class="stat-row">
      <StatCard
        label="碳排放指标"
        :value="fmtNum(emissionLimitT ?? 0)"
        unit="tCO₂e"
        icon="target"
        color="primary"
      />
      <StatCard
        label="计划碳排"
        :value="fmtNum(plannedEmissionT)"
        unit="tCO₂e"
        icon="edit_calendar"
        color="warning"
      />
      <StatCard
        label="进度碳排"
        :value="fmtNum(actualEmissionT)"
        unit="tCO₂e"
        icon="trending_up"
        color="success"
      />
    </div>
  </div>

  <div v-if="submitErrorMessage" class="alert alert-error alert-sm mt-4" role="alert">
    <span class="material-symbols-outlined icon-sm">error</span>
    <span class="text-sm">{{ submitErrorMessage }}</span>
  </div>

  <div class="mt-auto pt-4">
    <!-- 计算按钮不禁用：无待提交批次时点击会提示，提交中重复点击被忽略 -->
    <button class="btn btn-primary btn-block" @click="handleCompleteDay">
      <span v-if="submitting" class="loading loading-spinner loading-xs"></span>
      <span v-else class="material-symbols-outlined">calculate</span>
      <span>{{ submitting ? '计算中...' : '计算' }}</span>
    </button>
  </div>
    </div>
  </div>
</template>
