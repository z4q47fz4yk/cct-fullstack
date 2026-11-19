<script setup lang="ts">
/**
 * UsageEntrySummary - 活动数据列表卡片（设计稿 view-entry-plan / view-entry-actual）
 *
 * 结构对齐 HTML 模板：card-head（标题 + 移除批次）、工具行（模板下载/导入/新增/
 * 批量删除 + 阶段 tab + 日期）、全宽数据表格（复选框 / 阶段 / 工序 / 资源名称 /
 * 用量 / 单位 / 单价 / 成本 / 碳排放因子 / 碳排放量 / 使用日期 / 操作）、底部分页。
 *
 * 数据行 = 当日已保存记录（当前口径） ∪ 待提交日报批次条目；
 * 导入 / 新增 / 编辑 / 删除 均立即写入后端并刷新列表（不再有"待提交手动行"），
 * 碳排放量 = 用量 × 碳排放因子 / 1000（与「碳排放计算结果」统计卡同口径）。
 *
 * 日报 store（stores/report.ts）由本组件直接读取；已保存记录由父组件传入。
 */
import { computed, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryCache } from '@pinia/colada'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useDailyReportStoreV2 } from '@/stores/report'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import {
  listResourcesQuery,
  listResourceUsagesQueryKey,
  parseDailyReportMutation,
  batchCreateResourceUsageMutation,
  updateResourceUsageMutation,
  deleteResourceUsageMutation,
} from '@/client/@pinia/colada.gen'
import type { ResourceUsageWithTagsResp, UsageType } from '@/client/types.gen'
import type { ResourceCategory } from '@/types/resource'
import { fmtNumber } from '@/utils/format'
import {
  isMonitorMaterialTemplate,
  parseMonitorMaterialTemplate,
  type MonitorUsageType,
} from '@/utils/monitorMaterialImport'
import {
  usageStageOf,
  USAGE_STAGE_LABEL,
  USAGE_STAGE_BADGE_CLS,
  type UsageStage,
} from '@/utils/usageStage'
import SegmentControl from '@/components/common/SegmentControl.vue'
import ResourceUsageEntryForm from './ResourceUsageEntryForm.vue'

/** Excel 导入解析出的资源用量行（保存前结构） */
interface ImportedUsageRow {
  task_id: number
  resource_id: number
  quantity: number
  usage_date?: string
  usage_type?: MonitorUsageType
}

/** 表格行：日报（待提交）或已保存记录 */
interface TableRow {
  /** 行 key（日报 = daily-taskId-resourceName；已保存 = usage-id） */
  key: string
  source: 'daily' | 'saved'
  /** 已保存记录 id（saved 专属，用于编辑/删除） */
  id?: number
  taskId: number
  resourceName: string
  /** 阶段（建材生产 / 建材运输 / 施工建造） */
  stage: UsageStage
  unit?: string
  quantity: number
  /** 使用日期（YYYY-MM-DD） */
  usageDate: string
  /** 手动行 key（已保存记录的勾选/编辑标识） */
  rowKey?: string
  /** 以下经资源映射补充（缺失显示 “—”） */
  unitPrice?: number | null
  carbonFactor?: number | null
}

const usageDate = defineModel<string>('usageDate', { required: true })

const { usageType, selectedTaskId, records } = defineProps<{
  /** 当前用量类型（决定列表标题与保存口径） */
  usageType: UsageType
  /** 左侧选中的施工工序（导入日报时分配目标；null = 项目（全部）） */
  selectedTaskId?: number | null
  /** 当前日期 + 口径的已保存记录（列表数据源，父组件查询） */
  records: ResourceUsageWithTagsResp[]
}>()

const { confirmDanger } = useConfirm()
const { notifySuccess, notifyError } = useToast()
const store = useDailyReportStoreV2()
const { currentProjectId } = useProjectContext()
const queryCache = useQueryCache()

// 任务名 / 资源名映射
const { tasks } = useScheduleApi()
const taskMap = computed(() => {
  const m = new Map<number, { code: string; name: string }>()
  for (const t of tasks.value) m.set(t.id, { code: t.code ?? '', name: t.name })
  return m
})
const { state: resourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: FETCH_ALL_PAGE_SIZE },
  }),
)
interface ResourceInfo {
  name: string
  unit: string
  category: ResourceCategory
  unitPrice: number
  carbonFactor: number
}
const resourceMap = computed<Map<number, ResourceInfo>>(() => {
  const m = new Map<number, ResourceInfo>()
  for (const r of resourcesState.value?.data?.items ?? []) {
    m.set(r.id, {
      name: r.name,
      unit: r.unit,
      category: r.category,
      unitPrice: r.unitPrice,
      carbonFactor: r.carbonFactor,
    })
  }
  return m
})
/** 按资源名反查（日报条目只有资源名，命中即可补齐单位/单价/因子）；key = 原始名与 trim 后名 */
const resourceIdByName = computed(() => {
  const m = new Map<string, number>()
  for (const [id, info] of resourceMap.value.entries()) {
    m.set(info.name, id)
    m.set(info.name.trim(), id)
  }
  return m
})
const resourceByName = computed(() => {
  const m = new Map<string, ResourceInfo>()
  for (const info of resourceMap.value.values()) m.set(info.name, info)
  return m
})

// ─── 立即保存：批量创建 / 更新 / 删除 ────────────────────────

const { mutateAsync: createBatch } = useMutation(batchCreateResourceUsageMutation())
const { mutateAsync: updateUsage } = useMutation(updateResourceUsageMutation())
const { mutateAsync: deleteUsage } = useMutation(deleteResourceUsageMutation())

/** 让所有（任意筛选组合）资源用量列表缓存刷新，父组件统计卡同步更新 */
async function invalidateUsages() {
  await queryCache.invalidateQueries({
    key: listResourceUsagesQueryKey({
      path: { project_id: currentProjectId.value! },
    }),
  })
}

const saving = ref(false)

/**
 * 导入行立即保存：
 * - 数量 <= 0 的行跳过（后端 422）
 * - 与当前已加载窗口（同日期同口径）重复的行跳过；跨日期重复由后端 409 拦截并提示
 */
async function saveImportedRows(rows: ImportedUsageRow[]) {
  const dateOf = (r: ImportedUsageRow) => r.usage_date ?? usageDate.value
  const typeOf = (r: ImportedUsageRow) => r.usage_type ?? usageType
  const keyOf = (r: ImportedUsageRow) =>
    `${r.task_id}|${r.resource_id}|${dateOf(r)}|${typeOf(r)}`

  const existingKeys = new Set(
    records.map((u) => `${u.taskId}|${u.resourceId}|${(u.usageDate ?? '').slice(0, 10)}|${u.usageType}`),
  )

  const valid: ImportedUsageRow[] = []
  let skippedDup = 0
  let skippedQty = 0
  for (const r of rows) {
    if (!(r.quantity > 0)) {
      skippedQty++
      continue
    }
    if (existingKeys.has(keyOf(r))) {
      skippedDup++
      continue
    }
    valid.push(r)
  }

  if (valid.length === 0) {
    notifyError({
      title: '没有可保存的数据',
      description:
        skippedDup > 0
          ? `${skippedDup} 行与已保存记录重复，已跳过`
          : '请检查数量是否有效',
    })
    return
  }

  saving.value = true
  try {
    await createBatch({
      path: { project_id: currentProjectId.value! },
      body: {
        name: `Excel导入 - ${usageDate.value}`,
        items: valid.map((r) => ({
          task_id: r.task_id,
          resource_id: r.resource_id,
          usage_date: dateOf(r),
          quantity: r.quantity,
          usage_type: typeOf(r),
        })),
      },
    })
    await invalidateUsages()
    notifySuccess({
      title: '导入成功',
      description: `已保存 ${valid.length} 条资源用量${
        skippedDup > 0 || skippedQty > 0
          ? `（跳过重复 ${skippedDup} 条、无效数量 ${skippedQty} 条）`
          : ''
      }`,
    })
  } catch (e) {
    const err = e as { status?: number }
    await invalidateUsages()
    notifyError({
      title: '保存失败',
      description:
        err?.status === 409
          ? '部分记录与已有数据重复（同工序同资源同日期同口径），已保存的记录已刷新'
          : err?.status === 422
            ? '存在无效的工序或资源引用，请检查后再试'
            : e instanceof Error
              ? e.message
              : '请检查文件内容',
    })
  } finally {
    saving.value = false
  }
}

// ─── 导入（设计稿：点击直接选取 Excel，解析后立即保存） ──────

const importFileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const { mutateAsync: parseDailyReport } = useMutation(parseDailyReportMutation())

const TEMPLATE_URL = `/templates/${encodeURIComponent('碳排放施工监测材料模板.xlsx')}`

function openImportPicker() {
  importFileInput.value?.click()
}

async function handleImportFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || importing.value) return
  if (!/\.(xlsx|xls|csv)$/i.test(file.name)) {
    notifyError({ title: '文件格式不支持', description: '请选择 .xlsx / .xls / .csv 文件' })
    return
  }

  importing.value = true
  try {
    const buffer = await file.arrayBuffer()
    // 监测材料模板（分部工程/时间/名称/规格型号/单位/数量[/口径]）→ 前端直接解析
    if (isMonitorMaterialTemplate(buffer)) {
      await importMonitorMaterial(buffer)
      return
    }
    await importDailyReport(file)
  } catch (e) {
    notifyError({
      title: '导入解析失败',
      description: e instanceof Error ? e.message : '请检查文件内容',
    })
  } finally {
    importing.value = false
  }
}

// ─── 监测材料模板导入（前端解析：分部工程 → 工序、名称 → 资源） ──

/** 分部工程名 → 工序 id（精确名优先，其次互相包含的模糊匹配） */
function matchTaskIdByDivision(division: string): number | null {
  const list = tasks.value
  const exact = list.find((t) => t.name.trim() === division)
  if (exact) return exact.id
  const fuzzy = list.find(
    (t) => t.name.length >= 2 && (t.name.includes(division) || division.includes(t.name)),
  )
  return fuzzy?.id ?? null
}

async function importMonitorMaterial(buffer: ArrayBuffer) {
  const { rows, errors } = parseMonitorMaterialTemplate(buffer)
  if (rows.length === 0) {
    notifyError({
      title: '未解析到有效数据行',
      description: errors.slice(0, 3).join('；') || '请按模板要求填写后再导入',
    })
    return
  }

  // 分部工程 → 工序
  const taskIdByDivision = new Map<string, number>()
  const unmatchedDivisions: string[] = []
  for (const division of new Set(rows.map((r) => r.division))) {
    const id = matchTaskIdByDivision(division)
    if (id == null) unmatchedDivisions.push(division)
    else taskIdByDivision.set(division, id)
  }

  // 行 → 保存行（同工序同资源同日期同口径合并数量）
  const merged = new Map<string, ImportedUsageRow>()
  const unmatchedResources: string[] = []
  let skipped = 0
  for (const r of rows) {
    const taskId = taskIdByDivision.get(r.division)
    const resourceId =
      resourceIdByName.value.get(r.name) ?? resourceIdByName.value.get(r.name.trim())
    if (taskId == null || resourceId == null) {
      skipped++
      if (resourceId == null && !unmatchedResources.includes(r.name)) {
        unmatchedResources.push(r.name)
      }
      continue
    }
    const key = `${taskId}|${resourceId}|${r.date ?? usageDate.value}|${r.usageType ?? usageType}`
    const existing = merged.get(key)
    if (existing) existing.quantity += r.quantity
    else
      merged.set(key, {
        task_id: taskId,
        resource_id: resourceId,
        quantity: r.quantity,
        usage_date: r.date ?? undefined,
        usage_type: r.usageType ?? undefined,
      })
  }

  const imported = Array.from(merged.values()).filter((r) => r.quantity !== 0)
  const problems: string[] = []
  if (unmatchedDivisions.length > 0) {
    problems.push(
      `分部工程未匹配工序（已跳过 ${skipped} 行）：${unmatchedDivisions.slice(0, 5).join('、')}${unmatchedDivisions.length > 5 ? ' 等' : ''}`,
    )
  }
  if (unmatchedResources.length > 0) {
    problems.push(
      `名称未匹配资源（已跳过）：${unmatchedResources.slice(0, 5).join('、')}${unmatchedResources.length > 5 ? ' 等' : ''}`,
    )
  }
  problems.push(...errors.slice(0, 3))

  if (imported.length > 0) {
    await saveImportedRows(imported)
  } else {
    notifyError({ title: '没有可保存的数据', description: problems.join('；') || '请检查模板内容' })
    return
  }
  if (problems.length > 0) {
    notifyError({ title: '导入存在问题', description: problems.join('；') })
  }
}

// ─── 施工日报导入（后端解析：需先选择目标工序，保存到当前工序） ──

async function importDailyReport(file: File) {
  if (selectedTaskId == null) {
    notifyError({ title: '请先选择工序', description: '在左侧「施工工序」中选择一个工序后再导入' })
    return
  }
  const result = await parseDailyReport({
    path: { project_id: currentProjectId.value! },
    body: { file, usage_date: usageDate.value, config_id: null },
  })
  // 按资源名匹配项目资源（同名数量合并）；未匹配的列出提示
  const merged = new Map<number, number>()
  const unmatched: string[] = []
  for (const item of result.parsedItems) {
    const resourceId = resourceIdByName.value.get(item.resourceName)
    if (resourceId === undefined) {
      if (!unmatched.includes(item.resourceName)) unmatched.push(item.resourceName)
      continue
    }
    merged.set(resourceId, (merged.get(resourceId) ?? 0) + item.quantity)
  }
  const rows: ImportedUsageRow[] = Array.from(merged.entries())
    .filter(([, qty]) => qty !== 0)
    .map(([resource_id, quantity]) => ({ task_id: selectedTaskId, resource_id, quantity }))
  if (unmatched.length > 0) {
    notifyError({
      title: `${result.parsedItems.length} 项中 ${unmatched.length} 项未匹配资源`,
      description: `请先在「基础数据」中添加：${unmatched.slice(0, 5).join('、')}${unmatched.length > 5 ? ' 等' : ''}`,
    })
  }
  if (rows.length > 0) await saveImportedRows(rows)
}

// ─── 数据源归一化（摊平为表格行） ────────────────────────────

const tableRows = computed<TableRow[]>(() => {
  const rows: TableRow[] = []
  for (const [taskId, resourceQuantities] of store.allocatedResourceQuantities.entries()) {
    for (const [resourceName, quantity] of Object.entries(resourceQuantities)) {
      if (quantity === 0) continue
      const res = resourceByName.value.get(resourceName)
      rows.push({
        key: `daily-${taskId}-${resourceName}`,
        source: 'daily',
        taskId,
        resourceName,
        stage: usageStageOf(resourceName, res?.category),
        unit: res?.unit,
        quantity,
        usageDate: usageDate.value,
        unitPrice: res?.unitPrice ?? null,
        carbonFactor: res?.carbonFactor ?? null,
      })
    }
  }
  for (const u of records) {
    const res = resourceMap.value.get(u.resourceId)
    rows.push({
      key: `usage-${u.id}`,
      source: 'saved',
      id: u.id,
      taskId: u.taskId,
      resourceName: res?.name ?? `资源 #${u.resourceId}`,
      stage: usageStageOf(res?.name ?? '', res?.category),
      unit: res?.unit,
      quantity: u.quantity,
      rowKey: `usage-${u.id}`,
      usageDate: (u.usageDate ?? '').slice(0, 10) || usageDate.value,
      unitPrice: res?.unitPrice ?? null,
      carbonFactor: res?.carbonFactor ?? null,
    })
  }
  return rows
})

/** 阶段筛选（当前数据无阶段字段：仅「全部」有数据，其余显示空态） */
const STAGE_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'production', label: '建材生产' },
  { value: 'transport', label: '建材运输' },
  { value: 'construction', label: '施工建造' },
] as const
const stageFilter = ref<(typeof STAGE_OPTIONS)[number]['value']>('all')
/** 工序（左侧侧栏）+ 阶段筛选：对列表同时生效 */
const filteredRows = computed(() => {
  let rows = tableRows.value
  if (selectedTaskId != null) rows = rows.filter((r) => r.taskId === selectedTaskId)
  if (stageFilter.value !== 'all') rows = rows.filter((r) => r.stage === stageFilter.value)
  return rows
})

// ─── 勾选与批量删除（仅已保存记录可勾选） ──────────────────────

const selectedKeys = ref<Set<string>>(new Set())
const selectableKeys = computed(() =>
  tableRows.value.filter((r) => r.rowKey).map((r) => r.rowKey as string),
)
const allSelected = computed(
  () =>
    selectableKeys.value.length > 0 &&
    selectableKeys.value.every((k) => selectedKeys.value.has(k)),
)
const someSelected = computed(
  () =>
    !allSelected.value &&
    selectableKeys.value.some((k) => selectedKeys.value.has(k)),
)

function toggleRow(key: string) {
  const next = new Set(selectedKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selectedKeys.value = next
}

function toggleAll() {
  selectedKeys.value = allSelected.value
    ? new Set()
    : new Set(selectableKeys.value)
}

async function handleBatchRemove() {
  if (selectedKeys.value.size === 0) {
    notifyError({ title: '请先勾选要删除的数据' })
    return
  }
  const r = await confirmDanger(`确定要删除所选 ${selectedKeys.value.size} 条数据吗？`)
  if (!r.confirmed) return
  const ids = tableRows.value
    .filter((row) => row.rowKey && selectedKeys.value.has(row.rowKey))
    .map((row) => row.id)
    .filter((id): id is number => id != null)
  saving.value = true
  let failed = 0
  try {
    for (const id of ids) {
      try {
        await deleteUsage({ path: { project_id: currentProjectId.value!, id } })
      } catch {
        failed++
      }
    }
    await invalidateUsages()
    notifySuccess({
      title: '删除完成',
      description: `已删除 ${ids.length - failed} 条${failed > 0 ? `，${failed} 条失败` : ''}`,
    })
  } finally {
    saving.value = false
    selectedKeys.value = new Set()
  }
}

// 记录减少时清理已选 key
watch(
  () => tableRows.value.length,
  () => {
    const valid = new Set(selectableKeys.value)
    for (const key of selectedKeys.value) {
      if (!valid.has(key)) selectedKeys.value.delete(key)
    }
  },
)

// ─── 分页（客户端，10 条/页，设计稿 pager） ─────────────────

const PAGE_SIZE = 10
const page = ref(1)
const totalRows = computed(() => filteredRows.value.length)
const pages = computed(() => Math.max(1, Math.ceil(totalRows.value / PAGE_SIZE)))
watch([pages, stageFilter], ([p]) => {
  if (page.value > p) page.value = p
})
const pagedRows = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return filteredRows.value.slice(start, start + PAGE_SIZE)
})
const pageNumbers = computed(() => {
  const total = pages.value
  const cur = page.value
  const window = 5
  let start = Math.max(1, cur - Math.floor(window / 2))
  const end = Math.min(total, start + window - 1)
  start = Math.max(1, end - window + 1)
  return Array.from({ length: end - start + 1 }, (_, i) => start + i)
})

// ─── 日报批次状态（「移除批次」入口在 card-head） ─────────────

const hasPendingBatch = computed(() => !!store.batchId && store.resourceUsages.length > 0)
const listTitle = computed(() =>
  usageType === 'ACTUAL' ? '实际活动数据列表' : '计划活动数据列表',
)

// ─── 新增 / 编辑（立即保存） ────────────────────────────────

const showEditModal = ref(false)
const editingRecord = ref<ResourceUsageWithTagsResp | null>(null)

function handleAdd() {
  editingRecord.value = null
  showEditModal.value = true
}

function handleEdit(row: TableRow) {
  editingRecord.value = records.find((u) => u.id === row.id) ?? null
  showEditModal.value = true
}

async function handleSubmitEdit(data: {
  task_id?: number
  resource_id?: number
  quantity?: number
}) {
  const taskId = data.task_id ?? editingRecord.value?.taskId
  const resourceId = data.resource_id ?? editingRecord.value?.resourceId
  const quantity = data.quantity ?? editingRecord.value?.quantity
  if (taskId == null || resourceId == null || quantity == null) return

  saving.value = true
  try {
    if (editingRecord.value) {
      await updateUsage({
        path: { project_id: currentProjectId.value!, id: editingRecord.value.id },
        body: { taskId, resourceId, quantity },
      })
      notifySuccess({ title: '已保存修改' })
    } else {
      await createBatch({
        path: { project_id: currentProjectId.value! },
        body: {
          name: `手动录入 - ${usageDate.value}`,
          items: [
            {
              task_id: taskId,
              resource_id: resourceId,
              usage_date: usageDate.value,
              quantity,
              usage_type: usageType,
            },
          ],
        },
      })
      notifySuccess({ title: '新增成功', description: '已保存 1 条资源用量' })
    }
    await invalidateUsages()
    showEditModal.value = false
    editingRecord.value = null
  } catch (e) {
    const err = e as { status?: number }
    await invalidateUsages()
    notifyError({
      title: '保存失败',
      description:
        err?.status === 409
          ? '同一任务在同一天同一类型已存在该资源记录'
          : err?.status === 422
            ? '存在无效的工序或资源引用，请检查后再试'
            : e instanceof Error
              ? e.message
              : '请稍后重试',
    })
  } finally {
    saving.value = false
  }
}

async function handleRemoveRow(row: TableRow) {
  if (row.id == null) return
  const r = await confirmDanger('确定要删除这条资源用量记录吗？')
  if (!r.confirmed) return
  saving.value = true
  try {
    await deleteUsage({ path: { project_id: currentProjectId.value!, id: row.id } })
    await invalidateUsages()
    notifySuccess({ title: '已删除' })
  } catch {
    notifyError({ title: '删除失败', description: '请稍后重试' })
  } finally {
    saving.value = false
  }
}

async function handleRemoveBatch() {
  const r = await confirmDanger(
    '确定要移除这个待提交的日报批次吗？已解析的资源映射与分配数据将一并清除，需重新导入。',
  )
  if (!r.confirmed) return
  // 日报批次未落库，仅清空本地暂存（等价于原「移除批次」）
  store.reset()
}

// ─── 展示辅助 ──────────────────────────────────────────────

function taskDisplay(taskId: number) {
  const t = taskMap.value.get(taskId)
  if (!t) return `工序 #${taskId}`
  return t.code ? `${t.code} - ${t.name}` : t.name
}

/** 金额：千分位 + 两位小数；未知显示 “—” */
function fmtMoney(v: number | null | undefined): string {
  return v == null ? '—' : fmtNumber(v, 2)
}

function rowCost(row: TableRow): string {
  if (row.unitPrice == null) return '—'
  return fmtNumber(row.quantity * row.unitPrice, 2)
}

function fmtFactor(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(4)
}

/** 碳排放量（tCO₂）= 用量 × 因子 / 1000 */
function rowEmission(row: TableRow): string {
  if (row.carbonFactor == null) return '—'
  return fmtNumber((row.quantity * row.carbonFactor) / 1000, 2)
}
</script>

<template>
  <div class="panel p-0 flex flex-col">
    <!-- card-head：标题 + 移除批次 -->
    <div class="card-head">
      <div class="card-title">{{ listTitle }}</div>
      <button
        v-if="hasPendingBatch"
        type="button"
        class="action-text action-delete"
        @click="handleRemoveBatch"
      >
        移除批次
      </button>
    </div>

    <!-- 工具行（设计稿：模板下载/导入/新增/批量删除 与 阶段筛选同一行、居左、等高） -->
    <div
      class="filter-row flex flex-wrap items-center gap-2.5 px-4 py-3 border-b border-base-content/5"
    >
      <a
        :href="TEMPLATE_URL"
        download="碳排放施工监测材料模板.xlsx"
        class="btn btn-outline gap-1"
        title="下载碳排放施工监测材料模板（.xlsx）"
      >
        <span class="material-symbols-outlined icon-sm">download</span>
        模板下载
      </a>
      <button
        type="button"
        class="btn btn-outline gap-1"
        :disabled="importing"
        title="选择 Excel 文件导入：支持碳排放施工监测材料模板 / 施工日报"
        @click="openImportPicker"
      >
        <span v-if="importing" class="loading loading-spinner loading-xs" />
        <span v-else class="material-symbols-outlined icon-sm">upload_file</span>
        {{ importing ? '导入中' : '导入' }}
      </button>
      <input
        ref="importFileInput"
        type="file"
        accept=".xlsx,.xls,.csv"
        class="hidden"
        aria-label="选择要导入的 Excel 文件"
        @change="handleImportFileChange"
      />
      <button type="button" class="btn btn-primary gap-1" @click="handleAdd">
        <span class="material-symbols-outlined icon-sm">add</span>
        新增
      </button>
      <button
        type="button"
        class="btn btn-outline gap-1 !text-error !border-error/40 hover:!bg-error/10"
        @click="handleBatchRemove"
      >
        <span class="material-symbols-outlined icon-sm">delete</span>
        批量删除
      </button>
      <span class="w-px h-6 bg-base-content/10 mx-1" aria-hidden="true" />
      <SegmentControl
        v-model="stageFilter"
        :options="[...STAGE_OPTIONS]"
        size="sm"
        aria-label="阶段筛选"
      />
      <label class="input flex items-center gap-2 w-40 ml-auto">
        <span class="text-xs text-fg-muted shrink-0">日期</span>
        <input
          type="date"
          :value="usageDate"
          class="w-full bg-transparent outline-none"
          @change="
            (e) => (usageDate = (e.target as HTMLInputElement).value)
          "
        />
      </label>
    </div>

    <!-- 数据表格（设计稿列结构；区域随卡片拉伸，占满剩余高度） -->
    <div class="overflow-auto flex-1 min-h-0">
      <table class="table">
        <thead>
          <tr>
            <th class="w-10">
              <input
                type="checkbox"
                class="checkbox checkbox-sm"
                :checked="allSelected"
                :indeterminate="someSelected"
                aria-label="全选"
                @change="toggleAll"
              />
            </th>
            <th>阶段</th>
            <th>工序</th>
            <th>资源名称</th>
            <th class="table-num">用量</th>
            <th>单位</th>
            <th class="table-num">单价（元）</th>
            <th class="table-num">成本（元）</th>
            <th class="table-num">碳排放因子</th>
            <th class="table-num">碳排放量(tCO₂)</th>
            <th>使用日期</th>
            <th class="w-[120px]">操作</th>
          </tr>
        </thead>
        <tbody v-if="pagedRows.length > 0">
          <tr v-for="row in pagedRows" :key="row.key">
            <td>
              <input
                v-if="row.rowKey"
                type="checkbox"
                class="checkbox checkbox-sm"
                :checked="selectedKeys.has(row.rowKey)"
                :aria-label="`选择 ${row.resourceName}`"
                @change="toggleRow(row.rowKey!)"
              />
            </td>
            <td>
              <span
                class="text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
                :class="USAGE_STAGE_BADGE_CLS[row.stage]"
              >
                {{ USAGE_STAGE_LABEL[row.stage] }}
              </span>
            </td>
            <td class="whitespace-nowrap">{{ taskDisplay(row.taskId) }}</td>
            <td class="font-medium whitespace-nowrap">{{ row.resourceName }}</td>
            <td class="table-num">{{ fmtNumber(row.quantity, 2) }}</td>
            <td>{{ row.unit ?? '—' }}</td>
            <td class="table-num">{{ fmtMoney(row.unitPrice) }}</td>
            <td class="table-num">{{ rowCost(row) }}</td>
            <td class="table-num">{{ fmtFactor(row.carbonFactor) }}</td>
            <td class="table-num">{{ rowEmission(row) }}</td>
            <td class="text-fg-muted whitespace-nowrap">{{ row.usageDate }}</td>
            <td>
              <template v-if="row.source === 'saved'">
                <button type="button" class="action-text" @click="handleEdit(row)">编辑</button>
                <button type="button" class="action-text action-delete" @click="handleRemoveRow(row)">
                  删除
                </button>
              </template>
              <span v-else class="badge badge-sm badge-neutral">日报</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="pagedRows.length === 0" class="py-10 text-center text-sm text-fg-subtle">
        {{
          stageFilter === 'all' && selectedTaskId == null
            ? '暂无数据，点击新增或导入进行数据补充'
            : '暂无匹配数据'
        }}
      </div>
    </div>

    <!-- 分页（设计稿 pager） -->
    <div
      v-if="totalRows > 0"
      class="flex items-center justify-between px-4 py-3 text-[13px] text-fg-muted border-t border-base-content/5"
    >
      <span>共 {{ totalRows }} 条<span v-if="pages > 1"> · 第 {{ page }}/{{ pages }} 页</span></span>
      <div v-if="pages > 1" class="flex items-center gap-1">
        <button
          type="button"
          class="btn btn-sm min-w-7"
          :disabled="page <= 1"
          aria-label="上一页"
          @click="page--"
        >
          ‹
        </button>
        <button
          v-for="p in pageNumbers"
          :key="p"
          type="button"
          class="btn btn-sm min-w-7"
          :class="{ 'btn-primary': p === page }"
          @click="page = p"
        >
          {{ p }}
        </button>
        <button
          type="button"
          class="btn btn-sm min-w-7"
          :disabled="page >= pages"
          aria-label="下一页"
          @click="page++"
        >
          ›
        </button>
      </div>
    </div>

    <!-- 新增/编辑弹窗 -->
    <ResourceUsageEntryForm
      v-model:show="showEditModal"
      :mode="editingRecord ? 'update' : 'create'"
      :usage-date="usageDate"
      :usage-type="usageType"
      :is-submitting="saving"
      :initial-value="
        editingRecord
          ? {
              task_id: editingRecord.taskId,
              resource_id: editingRecord.resourceId,
              quantity: editingRecord.quantity,
            }
          : null
      "
      :title="editingRecord ? '编辑活动数据' : '新增活动数据'"
      @submit="handleSubmitEdit"
      @cancel="(editingRecord = null)"
    />
  </div>
</template>

<style scoped>
/* 工具行等高：日期输入与按钮/分段筛选同高（36px） */
.filter-row .input {
  height: 2.25rem;
}
</style>
