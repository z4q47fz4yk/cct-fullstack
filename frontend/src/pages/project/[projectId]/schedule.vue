<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import PaginationBar from '@/components/common/PaginationBar.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import StatsOverview from '@/components/schedule/StatsOverview.vue'
import TaskTable from '@/components/schedule/TaskTable.vue'
import GanttChart, { type GanttChartItem } from '@/components/common/GanttChart.vue'
import AddPredecessorModal from '@/components/schedule/AddPredecessorModal.vue'
import ManagePredecessorsModal from '@/components/schedule/ManagePredecessorsModal.vue'
import TaskForm from '@/components/schedule/TaskForm.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useConfirm } from '@/composables/useConfirm'
import { sortTasksForGantt, calculateStartDay } from '@/utils/schedule'
import { formatHttpError } from '@/utils/error'
import { getThemeColors } from '@/utils/themeColors'
import type {
  TaskWithTagsResp,
  TaskCreate,
  TaskUpdate,
  AddPredecessorRequest,
} from '@/client/types.gen'

definePage({
  meta: {
    title: '施工工序管理',
    description: '任务编排、前置依赖与关键路径管理',
    icon: 'view_timeline',
    showInNav: true,
    navOrder: 2,
  },
})

// ──── 甘特图 Meta 类型 ─────────────────────────────────────

interface TaskGanttMeta {
  id: number
  code: string
  name: string
  completed: number
  isCritical: boolean | null
}

// ──── 视图状态 ─────────────────────────────────────────────

const currentView = ref<'list' | 'gantt'>('list')

const viewOptions: ReadonlyArray<SegmentOption<'list' | 'gantt'>> = [
  { value: 'list', label: '列表视图', icon: 'format_list_bulleted' },
  { value: 'gantt', label: '甘特视图', icon: 'reorder' },
]
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

// 搜索词变化时回到第一页，避免结果收缩后停留在空页
watch(searchQuery, () => {
  currentPage.value = 1
})

const {
  tasks,
  stats,
  isLoadingTasks,
  isSubmitting,
  tasksError,
  createTask,
  updateTask,
  deleteTask,
  addPredecessor,
  refreshTasks,
  refreshStats,
  useAvailablePredecessors,
} = useScheduleApi({ searchQuery })

const { currentProjectId } = useProjectContext()

// 服务端 ScheduleStats 不含关键路径数量，需从任务列表客户端计算
const criticalPathCount = computed(() => {
  return tasks.value.filter((t: TaskWithTagsResp) => t.isCritical).length
})

// ──── 甘特图：着色逻辑 ────────────────────────────────────

function getTaskColor(task: TaskWithTagsResp): string {
  const C = getThemeColors()
  // 关键路径 → 红；完成 → 绿；进行中 → 蓝；未开始 → 灰
  if (task.isCritical) return C.error
  if (task.completed >= 1) return C.success
  if (task.completed > 0) return C.info
  return C.label
}

// ──── 甘特图：数据转换 ────────────────────────────────────

const ganttItems = computed<GanttChartItem<TaskGanttMeta>[]>(() => {
  const sortedTasks = sortTasksForGantt(tasks.value)
  const taskMap = new Map<number, TaskWithTagsResp>()
  sortedTasks.forEach((t) => taskMap.set(t.id, t))

  return sortedTasks.map((task) => ({
    label: task.code ? `${task.code} ${task.name}` : task.name,
    startDay: calculateStartDay(task, taskMap),
    duration: task.duration,
    color: getTaskColor(task),
    meta: {
      id: task.id,
      code: task.code ?? '',
      name: task.name,
      completed: task.completed,
      isCritical: task.isCritical ?? false,
    },
  }))
})

// ──── 甘特图：Tooltip 模板 ────────────────────────────────

function formatGanttTooltip(item: GanttChartItem<TaskGanttMeta>): string {
  const { startDay, duration, meta } = item
  if (!meta) return ''
  const endDay = startDay + duration
  const percent = Math.round(meta.completed * 100)
  const C = getThemeColors()

  return `
    <div style="font-size:12px; line-height:1.6;">
      <div style="font-weight:600; margin-bottom:4px;">${meta.code} ${meta.name}</div>
      <div>开始时间：第 ${startDay} 天</div>
      <div>结束时间：第 ${endDay} 天</div>
      <div>工期：${duration} 天</div>
      <div>完成度：${percent}%</div>
      <div style="margin-top:4px;">
        <span style="background:${meta.isCritical ? C.error : C.success};
                      padding:1px 6px; border-radius:3px; font-size:10px;">
          ${meta.isCritical ? '关键路径' : '非关键'}
        </span>
      </div>
    </div>
  `
}

// ──── 分页 ────────────────────────────────────────────────

const paginatedTasks = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return tasks.value.slice(start, start + pageSize.value)
})

// ──── 模态框状态 ──────────────────────────────────────────

const showAddModal = ref(false)
const showEditModal = ref(false)
const showPredecessorModal = ref(false)
const showManagePredecessorModal = ref(false)
const currentTaskForEdit = ref<TaskWithTagsResp | null>(null)
const currentTaskForPredecessor = ref<TaskWithTagsResp | null>(null)

// 管理前置依赖模态框：只存任务 id，任务对象实时从已刷新的 tasks 派生，
// 保证删除/编辑/添加成功后模态框列表即时刷新，而非停留在打开时的旧快照
const managePredecessorTaskId = ref<number | null>(null)
const currentTaskForManage = computed<TaskWithTagsResp | null>(() =>
  managePredecessorTaskId.value == null
    ? null
    : (tasks.value.find((t) => t.id === managePredecessorTaskId.value) ?? null),
)
const formError = ref('')
// 页面级错误：用于删除 / 添加前置依赖等不归属某个表单的失败提示
const localError = ref('')

const { availablePredecessors } = useAvailablePredecessors(
  computed(() => currentTaskForPredecessor.value?.id),
)

const { confirmDanger } = useConfirm()

// ──── 操作处理 ────────────────────────────────────────────

const handleRefresh = () => {
  refreshTasks()
  refreshStats()
}

const handleCreateTask = async (data: TaskCreate | TaskUpdate) => {
  formError.value = ''
  try {
    await createTask({
      path: { project_id: currentProjectId.value! },
      body: data as TaskCreate,
      silent: true,
    })
    showAddModal.value = false
  } catch (e) {
    formError.value = formatHttpError(e, '创建任务失败，请重试')
    console.error('Create task failed:', e)
  }
}

const handleEditTask = (task: TaskWithTagsResp) => {
  currentTaskForEdit.value = task
  formError.value = ''
  showEditModal.value = true
}

const handleUpdateTask = async (data: TaskUpdate) => {
  if (!currentTaskForEdit.value) return
  formError.value = ''
  try {
    await updateTask({
      path: { project_id: currentProjectId.value!, id: currentTaskForEdit.value.id },
      body: data,
      silent: true,
    })
    showEditModal.value = false
    currentTaskForEdit.value = null
  } catch (e) {
    formError.value = formatHttpError(e, '更新任务失败，请重试')
    console.error('Update task failed:', e)
  }
}

// 追踪正在删除的任务 id，用于在表格中禁用该行按钮 + 显示 spinner
const deletingTaskId = ref<number | null>(null)
const handleDeleteTask = async (task: TaskWithTagsResp) => {
  localError.value = ''
  const result = await confirmDanger(`确定要删除任务 "${task.name}" 吗？`)
  if (!result.confirmed) return
  deletingTaskId.value = task.id
  try {
    await deleteTask({ path: { project_id: currentProjectId.value!, id: task.id } })
  } catch (e) {
    localError.value = formatHttpError(e, '删除失败，请重试')
    console.error('Delete task failed:', e)
  } finally {
    deletingTaskId.value = null
  }
}

const handleAddPredecessor = (task: TaskWithTagsResp) => {
  currentTaskForPredecessor.value = task
  showPredecessorModal.value = true
}

// 打开管理前置依赖模态框（查看 / 编辑 / 删除 / 添加）
const handleManagePredecessors = (task: TaskWithTagsResp) => {
  managePredecessorTaskId.value = task.id
  showManagePredecessorModal.value = true
}

// 管理模态框中点击"添加前置依赖"：关闭管理模态框，复用 AddPredecessorModal
const handleManageAddRequest = (task: TaskWithTagsResp) => {
  showManagePredecessorModal.value = false
  managePredecessorTaskId.value = null
  currentTaskForPredecessor.value = task
  showPredecessorModal.value = true
}

const handleAddPredecessorSubmit = async (payload: AddPredecessorRequest) => {
  if (!currentTaskForPredecessor.value) return
  try {
    await addPredecessor({
      path: { project_id: currentProjectId.value!, id: currentTaskForPredecessor.value.id },
      body: payload,
      silent: true,
    })
    showPredecessorModal.value = false
    currentTaskForPredecessor.value = null
  } catch (e) {
    localError.value = formatHttpError(e, '添加前置依赖失败，请重试')
    console.error('Add predecessor failed:', e)
  }
}

const closeAddModal = () => {
  showAddModal.value = false
  formError.value = ''
}

const closeEditModal = () => {
  showEditModal.value = false
  currentTaskForEdit.value = null
  formError.value = ''
}

const closePredecessorModal = () => {
  showPredecessorModal.value = false
  currentTaskForPredecessor.value = null
}

const closeManagePredecessorModal = () => {
  showManagePredecessorModal.value = false
  managePredecessorTaskId.value = null
}
</script>

<template>
  <!-- 操作工具条（设计稿 page-head toolbar：视图切换 / 添加任务） -->
  <div class="flex items-center justify-end gap-2 mb-4 flex-wrap">
    <SegmentControl
      v-model="currentView"
      :options="viewOptions"
      aria-label="任务视图"
      size="md"
    />
    <button class="btn btn-primary gap-1" :disabled="isLoadingTasks" @click="showAddModal = true">
      <span class="material-symbols-outlined icon-sm">add</span>
      添加任务
    </button>
  </div>

  <ErrorState
    v-if="tasksError"
    title="加载失败"
    description="无法获取任务列表，请检查网络连接"
    class="mb-4"
    @retry="handleRefresh"
  />

  <div v-if="localError" class="alert alert-error alert-sm mb-4" role="alert">
    <span class="material-symbols-outlined">error</span>
    <span>{{ localError }}</span>
  </div>

  <template v-else>
    <div v-if="stats" class="mb-4">
      <StatsOverview :stats :critical-path-count="criticalPathCount" />
    </div>

    <!-- 甘特图视图 -->
    <section
      v-if="currentView === 'gantt'"
      class="p-4 panel overflow-hidden"
      aria-labelledby="schedule-gantt-title"
    >
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <h2 id="schedule-gantt-title" class="section-title m-0">施工进度甘特图</h2>
        <!-- 图例（设计稿：关键路径 / 已完成 / 进行中 / 未开始） -->
        <div class="flex items-center gap-4 text-xs text-fg-muted">
          <span class="inline-flex items-center gap-1.5">
            <i class="w-2 h-2 rounded-full bg-error inline-block" />关键路径
          </span>
          <span class="inline-flex items-center gap-1.5">
            <i class="w-2 h-2 rounded-full bg-success inline-block" />已完成
          </span>
          <span class="inline-flex items-center gap-1.5">
            <i class="w-2 h-2 rounded-full bg-info inline-block" />进行中
          </span>
          <span class="inline-flex items-center gap-1.5">
            <i class="w-2 h-2 rounded-full bg-fg-subtle inline-block" />未开始
          </span>
        </div>
      </div>
      <div v-if="tasks.length === 0" class="py-8 flex flex-col items-center gap-3">
        <div class="w-16 h-16 rounded-full bg-base-300 flex items-center justify-center">
          <span class="material-symbols-outlined icon-2xl text-base-content/30">view_timeline</span>
        </div>
        <div class="text-center">
          <h3 class="text-lg font-semibold text-base-content/70">暂无任务</h3>
          <p class="text-sm text-fg-subtle mt-1">点击添加按钮创建第一个任务</p>
        </div>
      </div>
      <div v-else>
        <GanttChart
          :items="ganttItems"
          :total-days="stats?.criticalDuration ?? 30"
          :tooltip-formatter="formatGanttTooltip as (item: unknown) => string"
        />
      </div>
    </section>

    <!-- 列表视图 -->
    <template v-else>
      <section class="panel p-0 overflow-hidden" aria-labelledby="schedule-list-title">
        <!-- 头栏：标题 + 搜索 -->
        <div class="px-4 py-2.5 border-b border-base-content/10 flex flex-wrap items-center gap-3">
          <h2 id="schedule-list-title" class="section-title !mb-0">
            任务列表
            <span class="badge badge-sm">{{ tasks.length }} 个任务</span>
          </h2>
          <div class="ml-auto">
            <label class="input flex items-center gap-2 w-64">
              <span class="material-symbols-outlined icon-sm opacity-50" aria-hidden="true"
                >search</span
              >
              <input
                v-model.lazy="searchQuery"
                type="text"
                class="grow"
                placeholder="搜索任务名称..."
                aria-label="搜索任务名称"
                :disabled="isLoadingTasks"
              />
              <button
                v-if="searchQuery"
                type="button"
                class="material-symbols-outlined icon-sm cursor-pointer hover:text-error"
                aria-label="清除搜索"
                @click="searchQuery = ''"
              >
                close
              </button>
            </label>
          </div>
        </div>

        <div v-if="isLoadingTasks" class="flex justify-center py-8">
          <span class="loading loading-spinner loading-lg text-primary"></span>
        </div>

        <template v-else>
          <TaskTable
            :tasks="paginatedTasks"
            :deleting-id="deletingTaskId"
            @edit="handleEditTask"
            @delete="handleDeleteTask"
            @add-predecessor="handleAddPredecessor"
            @manage-predecessors="handleManagePredecessors"
          />
          <div v-if="pageSize > 10" class="border-t border-base-content/10">
            <PaginationBar
              v-model:current="currentPage"
              v-model:page-size="pageSize"
              :total="tasks.length"
            />
          </div>
        </template>
      </section>
    </template>
  </template>

  <!-- 管理前置任务模态框（查看 / 编辑 / 删除） -->
  <ManagePredecessorsModal
    v-model:open="showManagePredecessorModal"
    :current-task="currentTaskForManage"
    @add="handleManageAddRequest"
  />

  <!-- 添加前置任务模态框 -->
  <AddPredecessorModal
    v-model:open="showPredecessorModal"
    :current-task="currentTaskForPredecessor"
    :available-tasks="availablePredecessors"
    @add="handleAddPredecessorSubmit"
  />

  <!-- 添加任务模态框 -->
  <BaseModal v-model:open="showAddModal" title="添加新任务" class="max-w-lg" @close="closeAddModal">
    <TaskForm
      mode="create"
      :is-submitting
      :error="formError"
      @submit="handleCreateTask"
      @cancel="closeAddModal"
    />
  </BaseModal>

  <!-- 编辑任务模态框 -->
  <BaseModal v-model:open="showEditModal" title="编辑任务" class="max-w-lg" @close="closeEditModal">
    <TaskForm
      v-if="currentTaskForEdit"
      mode="edit"
      :initial-data="currentTaskForEdit"
      :is-submitting
      :error="formError"
      @submit="handleUpdateTask"
      @cancel="closeEditModal"
    />
  </BaseModal>
</template>
