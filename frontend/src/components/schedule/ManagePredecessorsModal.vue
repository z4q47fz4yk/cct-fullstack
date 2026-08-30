<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type {
  TaskWithTagsResp,
  TaskDependencyInfo,
  DependencyType,
  TaskDependencyUpdate,
} from '@/client/types.gen'
import { useProjectContext } from '@/composables/useProjectContext'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { useToast } from '@/composables/useToast'
import { formatHttpError } from '@/utils/error'
import { getSliceColor } from '@/utils/themeColors'

const { currentTask } = defineProps<{
  currentTask: TaskWithTagsResp | null
}>()

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  // 由父组件弹出 AddPredecessorModal 复用现有添加流程
  add: [task: TaskWithTagsResp]
}>()

const { currentProjectId } = useProjectContext()
const { updatePredecessor, removePredecessor, useAvailablePredecessors } = useScheduleApi()
const { notifySuccess, notifyError } = useToast()

// ──── 依赖类型元数据 ────────────────────────────────────────

interface DependencyOption {
  value: DependencyType
  label: string
  short: string
  description: string
}

const dependencyOptions: ReadonlyArray<DependencyOption> = [
  {
    value: 'FS',
    label: '完成-开始 (FS)',
    short: 'FS',
    description: '前置任务完成后，后续任务才能开始',
  },
  {
    value: 'SS',
    label: '开始-开始 (SS)',
    short: 'SS',
    description: '前置任务开始后，后续任务才能开始',
  },
  {
    value: 'FF',
    label: '完成-完成 (FF)',
    short: 'FF',
    description: '前置任务完成后，后续任务才能完成',
  },
]

function dependencyMeta(type: DependencyType): DependencyOption {
  return dependencyOptions.find((o) => o.value === type) ?? dependencyOptions[0]!
}

// ──── 行内编辑状态 ──────────────────────────────────────────

const editingId = ref<number | null>(null)
const editType = ref<DependencyType>('FS')

// 行级 loading 状态：用于删除按钮 / 编辑保存按钮的 spinner
const deletingId = ref<number | null>(null)
const savingId = ref<number | null>(null)

// 切换某行进入编辑态
function startEdit(predecessor: TaskDependencyInfo) {
  editingId.value = predecessor.id
  editType.value = predecessor.type
}

function cancelEdit() {
  editingId.value = null
}

// 保存编辑
async function saveEdit(predecessor: TaskDependencyInfo) {
  if (!currentTask) return
  savingId.value = predecessor.id
  // 与后端 TaskDependencyUpdate 语义保持一致：未变化的字段不发送
  const body: TaskDependencyUpdate = {}
  if (editType.value !== predecessor.type) body.type = editType.value

  // 如果没有变化，关闭编辑态即可
  if (Object.keys(body).length === 0) {
    editingId.value = null
    savingId.value = null
    return
  }

  try {
    await updatePredecessor({
      path: {
        project_id: currentProjectId.value!,
        id: currentTask.id,
        predecessor_id: predecessor.id,
      },
      body,
      silent: true,
    })
    notifySuccess({
      title: '依赖已更新',
      description: `${predecessor.code} ${predecessor.name}`,
    })
    editingId.value = null
  } catch (e) {
    notifyError({
      title: '更新失败',
      description: formatHttpError(e, '更新依赖失败，请重试'),
    })
    console.error('Update predecessor failed:', e)
  } finally {
    savingId.value = null
  }
}

// 删除依赖（无二次确认，删除后 toast 反馈）
async function handleRemove(predecessor: TaskDependencyInfo) {
  if (!currentTask) return
  deletingId.value = predecessor.id
  try {
    await removePredecessor({
      path: {
        project_id: currentProjectId.value!,
        id: currentTask.id,
        predecessor_id: predecessor.id,
      },
      silent: true,
    })
    notifySuccess({
      title: '依赖已移除',
      description: `${predecessor.code} ${predecessor.name}`,
    })
  } catch (e) {
    notifyError({
      title: '删除失败',
      description: formatHttpError(e, '删除依赖失败，请重试'),
    })
    console.error('Remove predecessor failed:', e)
  } finally {
    deletingId.value = null
  }
}

// ──── 添加依赖（事件转发到父组件） ──────────────────────────

function handleAddClick() {
  if (!currentTask) return
  emit('add', currentTask)
}

// ──── 关闭时清理编辑态 ──────────────────────────────────────

watch(open, (val) => {
  if (!val) {
    editingId.value = null
    deletingId.value = null
    savingId.value = null
  }
})

// 当前任务的依赖列表（响应式，跟随 currentTask 切换）
const predecessors = computed<TaskDependencyInfo[]>(() => currentTask?.predecessors ?? [])

// 依赖类型选项的简短描述（用于 tooltip）
const typeDescription = computed(() => dependencyMeta(editType.value).description)

// 当前可用前置任务（用于辅助说明）
const availableRef = computed(() => currentTask?.id)
const { availablePredecessors } = useAvailablePredecessors(availableRef)

// 关闭模态框
function closeModal() {
  open.value = false
}
</script>

<template>
  <dialog
    class="modal"
    :class="{ 'modal-open': open }"
    role="dialog"
    aria-modal="true"
    aria-labelledby="schedule-manage-predecessor-title"
  >
    <div class="modal-box max-w-lg">
      <!-- Header -->
      <header class="flex items-start justify-between gap-3 mb-4">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 text-sm text-fg-subtle">
            <span class="material-symbols-outlined icon-sm">link</span>
            <span>管理前置依赖</span>
          </div>
          <h3
            id="schedule-manage-predecessor-title"
            class="font-bold text-lg truncate"
            :title="currentTask?.name ?? ''"
          >
            <span
              v-if="currentTask?.code"
              class="badge badge-primary badge-sm align-middle mr-2"
              :class="{ 'badge-warning': currentTask.isCritical }"
            >
              {{ currentTask.code }}
            </span>
            {{ currentTask?.name }}
          </h3>
          <p class="text-xs text-fg-subtle mt-1">
            共 {{ predecessors.length }} 个前置依赖 · 可选
            {{ availablePredecessors.length }} 个候选任务
          </p>
        </div>
        <button
          type="button"
          class="btn btn-ghost btn-sm btn-square"
          aria-label="关闭"
          @click="closeModal"
        >
          <span class="material-symbols-outlined">close</span>
        </button>
      </header>

      <!-- 空状态 -->
      <div
        v-if="predecessors.length === 0"
        class="py-10 flex flex-col items-center gap-3 text-center"
      >
        <div class="w-16 h-16 rounded-full bg-base-300 flex items-center justify-center">
          <span class="material-symbols-outlined icon-2xl text-base-content/30"> link_off </span>
        </div>
        <div>
          <h3 class="text-base font-semibold text-base-content/70">暂无前置依赖</h3>
          <p class="text-sm text-fg-subtle mt-1">添加前置任务以定义工序间的执行顺序</p>
        </div>
      </div>

      <!-- 依赖列表 -->
      <ul v-else class="space-y-2 max-h-80 overflow-y-auto pr-1">
        <li
          v-for="(p, idx) in predecessors"
          :key="p.id"
          class="rounded-lg border border-base-300 bg-base-200/40 px-3 py-2.5"
        >
          <!-- 默认态 -->
          <div v-if="editingId !== p.id" class="flex items-center gap-2">
            <!-- 序号 / 色块 -->
            <div
              class="w-1.5 h-9 rounded-full shrink-0"
              :style="{ backgroundColor: getSliceColor(idx) }"
              aria-hidden="true"
            />
            <span class="badge badge-primary badge-sm shrink-0" :title="p.name">
              {{ p.code }}
            </span>
            <span class="flex-1 min-w-0 truncate text-sm" :title="p.name">
              {{ p.name }}
            </span>
            <!-- 类型摘要 -->
            <div class="flex items-center gap-1 shrink-0">
              <span
                class="badge badge-sm badge-outline font-num"
                :title="dependencyMeta(p.type).description"
              >
                {{ dependencyMeta(p.type).short }}
              </span>
            </div>
            <!-- 行操作 -->
            <div class="flex items-center gap-0.5 shrink-0">
              <button
                type="button"
                class="btn btn-ghost btn-xs btn-square"
                :disabled="deletingId === p.id"
                title="编辑"
                @click="startEdit(p)"
              >
                <span class="material-symbols-outlined icon-sm">edit</span>
              </button>
              <button
                type="button"
                class="btn btn-ghost btn-xs btn-square text-error hover:bg-error/10"
                :disabled="deletingId === p.id"
                :title="deletingId === p.id ? '正在删除...' : '删除依赖'"
                @click="handleRemove(p)"
              >
                <span v-if="deletingId === p.id" class="loading loading-spinner loading-xs" />
                <span v-else class="material-symbols-outlined icon-sm">delete</span>
              </button>
            </div>
          </div>

          <!-- 编辑态 -->
          <div v-else class="space-y-2">
            <div class="flex items-center gap-2">
              <div
                class="w-1.5 h-9 rounded-full shrink-0"
                :style="{ backgroundColor: getSliceColor(idx) }"
                aria-hidden="true"
              />
              <span class="badge badge-primary badge-sm shrink-0">{{ p.code }}</span>
              <span class="flex-1 min-w-0 truncate text-sm">{{ p.name }}</span>
            </div>

            <div class="grid grid-cols-1 gap-2">
              <!-- 类型 -->
              <div>
                <label class="text-xs text-fg-subtle mb-1 block">依赖类型</label>
                <select v-model="editType" class="select select-sm w-full">
                  <option v-for="opt in dependencyOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
            </div>

            <p class="text-xs text-fg-subtle flex items-center gap-1">
              <span class="material-symbols-outlined icon-sm">info</span>
              {{ typeDescription }}
            </p>

            <div class="flex items-center justify-end gap-1 pt-1">
              <button
                type="button"
                class="btn btn-ghost btn-xs"
                :disabled="savingId === p.id"
                @click="cancelEdit"
              >
                取消
              </button>
              <button
                type="button"
                class="btn btn-primary btn-xs gap-1"
                :disabled="savingId === p.id"
                @click="saveEdit(p)"
              >
                <span v-if="savingId === p.id" class="loading loading-spinner loading-xs" />
                <span v-else class="material-symbols-outlined icon-sm">check</span>
                保存
              </button>
            </div>
          </div>
        </li>
      </ul>

      <!-- Footer -->
      <div class="modal-action mt-4">
        <button type="button" class="btn btn-ghost btn-sm" @click="closeModal">关闭</button>
        <button
          type="button"
          class="btn btn-primary btn-sm gap-1"
          :disabled="!currentTask"
          @click="handleAddClick"
        >
          <span class="material-symbols-outlined icon-sm">add_link</span>
          添加前置依赖
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button @click="closeModal">close</button>
    </form>
  </dialog>
</template>
