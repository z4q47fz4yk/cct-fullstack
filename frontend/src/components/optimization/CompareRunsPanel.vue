<script setup lang="ts">
/**
 * 对比运行选择面板（紧凑版）
 *
 * 行内 pin 交互：点行尾 pin 图标把该解集设为基线（移到列表第一个，FLIP 动画）；
 * 已有基线时点任意兼容解集即与该基线对比（再点别的解集则换对比对象重新合并）；
 * 点基线行的 pin 取消基线。无基线时单击解集 = 切换解集（查看该运行结果）。
 *
 * 可对比性按任务/依赖快照一致性判定：与基线快照不一致的运行被禁用并沉底。
 * 所有状态的运行均可删除（FAIL 行同样可删）。
 */
import { computed, ref } from 'vue'
import { useInsightsStore } from '@/stores/insights'
import { useParetoCompare } from '@/composables/useParetoCompare'
import { useConfirm } from '@/composables/useConfirm'
import LoadingState from '@/components/common/LoadingState.vue'
import type { RunStatusEnum } from '@/client/types.gen'

const store = useInsightsStore()
const compare = useParetoCompare()
const { confirmDanger } = useConfirm()

const STATUS_LABEL: Record<RunStatusEnum, { text: string; cls: string }> = {
  PENDING: { text: '排队中', cls: 'bg-info/10 text-info' },
  RUNNING: { text: '运行中', cls: 'bg-info/10 text-info' },
  SUCCESS: { text: '已完成', cls: 'bg-success/10 text-success' },
  FAILURE: { text: '失败', cls: 'bg-error/10 text-error' },
}

function formatCreatedAt(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ──── 行内改名 ──────────────────────────────────────────────

const editingId = ref<string | null>(null)
const draftName = ref('')

function startRename(runId: string, currentName: string) {
  editingId.value = runId
  draftName.value = currentName
}

async function commitRename() {
  if (!editingId.value) return
  const runId = editingId.value
  const next = draftName.value.trim()
  const prev = compare.runLabel(runId)
  editingId.value = null
  if (next !== prev) {
    await compare.renameRun(runId, next.length > 0 ? next : null)
  }
}

// ──── 删除运行（任意状态可删） ──────────────────────────────

const deletingId = ref<string | null>(null)

async function handleDeleteRun(runId: string) {
  const r = await confirmDanger(
    `确定要删除运行「${compare.runLabel(runId)}」吗？此操作不可撤销。`,
    '删除运行',
  )
  if (!r.confirmed) return
  deletingId.value = runId
  try {
    await compare.deleteRun(runId)
  } finally {
    deletingId.value = null
  }
}

// ──── 行状态 ────────────────────────────────────────────────

const baselineId = computed(() => compare.compareRunIds.value[0] ?? null)

/** 是否可点击：仅 SUCCESS，且未与基线快照不兼容 */
function isRunSelectable(runId: string): boolean {
  const run = compare.runById.value.get(runId)
  if (!run || run.status !== 'SUCCESS') return false
  return !compare.incompatibleRunIds.value.has(runId)
}

/** 行高亮：基线/对比目标已勾选；无基线时高亮当前查看的运行 */
function isRowSelected(runId: string): boolean {
  return baselineId.value
    ? compare.compareRunIds.value.includes(runId)
    : store.currentRunId === runId
}

/** 槽位号：1=基线，2=对比目标 */
function slotIndex(runId: string): 1 | 2 | null {
  const idx = compare.compareRunIds.value.indexOf(runId)
  if (idx === 0) return 1
  if (idx === 1) return 2
  return null
}

/** 列表顺序：基线 → 可选（SUCCESS 且兼容）→ 禁用（非 SUCCESS + 不兼容）沉底 */
const orderedRuns = computed(() => {
  const enabled: typeof store.records = []
  const disabled: typeof store.records = []
  for (const run of store.records) {
    ;(isRunSelectable(run.id) ? enabled : disabled).push(run)
  }
  if (baselineId.value) {
    const i = enabled.findIndex((r) => r.id === baselineId.value)
    if (i > 0) enabled.unshift(enabled.splice(i, 1)[0]!)
  }
  return [...enabled, ...disabled]
})

function onRowClick(runId: string) {
  if (!isRunSelectable(runId)) return
  if (baselineId.value) {
    // 有基线：与该基线对比（第二个可换）
    compare.compareWith(runId)
  } else if (store.currentRunId !== runId) {
    // 无基线：切换解集
    store.currentRunId = runId
    store.selectedSolutionId = null
  }
}

function onPinClick(runId: string) {
  if (isRunSelectable(runId)) compare.setBaseline(runId)
}

function disableTitle(runId: string): string {
  const run = compare.runById.value.get(runId)
  if (run && run.status !== 'SUCCESS') return ''
  if (compare.incompatibleRunIds.value.has(runId)) return '任务快照不同，不可与基线对比'
  return ''
}
</script>

<template>
  <div class="flex flex-col gap-3 min-h-0">
    <!-- 状态行 -->
    <div class="flex items-center gap-2 min-w-0">
      <span
        v-if="compare.isCheckingSnapshots.value"
        class="flex items-center gap-1.5 text-xs text-fg-muted"
      >
        <span class="loading loading-spinner loading-xs text-primary"></span>
        正在校验快照可对比性…
      </span>
      <span
        v-else-if="compare.isMerging.value"
        class="flex items-center gap-1.5 text-sm text-fg-muted"
      >
        <span class="loading loading-spinner loading-sm text-primary"></span>
        正在自动合并两个运行…
      </span>
      <span
        v-else-if="compare.hasMerged.value"
        class="flex items-center gap-1.5 text-sm"
        :class="compare.mergedSolutions.value.length > 0 ? 'text-success' : 'text-fg-muted'"
      >
        <span class="material-symbols-outlined icon-sm">check_circle</span>
        已合并：{{ compare.mergedSolutions.value.length }} 个非支配解
      </span>
      <span v-else-if="baselineId" class="text-xs text-fg-muted truncate">
        基线：{{ compare.runLabel(baselineId) }} — 点击任意运行与之对比
      </span>
      <span v-else class="text-xs text-fg-muted truncate">
        点击行切换解集 · 点行尾 pin 图标设为基线
      </span>
    </div>

    <!-- 槽位行：基线/对比目标（带 pin 动画） -->
    <div
      v-if="compare.compareRunIds.value.length > 0"
      class="flex items-center gap-2 text-xs font-mono text-fg-subtle flex-wrap"
    >
      <TransitionGroup name="pin" tag="div" class="flex items-center gap-2 flex-wrap">
        <span
          v-for="(id, idx) in compare.compareRunIds.value"
          :key="id"
          class="flex items-center gap-1.5"
        >
          <span
            class="text-[10px] px-1.5 py-0.5 rounded-full font-sans shrink-0"
            :class="idx === 0 ? 'bg-primary/15 text-primary' : 'bg-cyan/15 text-cyan'"
          >
            {{ idx === 0 ? '① 基线' : '② 对比' }}
          </span>
          {{ compare.runLabel(id) }}
        </span>
      </TransitionGroup>
    </div>

    <!-- 运行列表（无对比统计且宽度大时两列，行重排带 FLIP 动画） -->
    <div class="max-h-64 overflow-y-auto min-h-0">
      <LoadingState v-if="store.isLoadingRecords" variant="skeleton">
        <div v-for="i in 3" :key="i" class="skeleton h-12 w-full rounded-lg"></div>
      </LoadingState>

      <div v-else-if="store.records.length === 0" class="text-sm text-fg-muted text-center py-4">
        暂无历史运行，请先运行优化
      </div>

      <TransitionGroup
        v-else
        name="flip"
        tag="div"
        class="grid grid-cols-1 gap-1.5"
        :class="compare.compareRunIds.value.length === 2 ? '' : 'xl:grid-cols-2'"
      >
        <div
          v-for="run in orderedRuns"
          :key="run.id"
          class="flex items-center gap-2.5 p-2 rounded-md border border-base-300/60 select-none transition-colors"
          :class="{
            'border-primary/50 bg-primary/5': isRowSelected(run.id),
            'cursor-pointer': isRunSelectable(run.id),
            'cursor-not-allowed': !isRunSelectable(run.id),
          }"
          :title="disableTitle(run.id)"
          @click="!editingId && onRowClick(run.id)"
        >
          <span
            class="material-symbols-outlined icon-sm"
            :class="
              !isRunSelectable(run.id)
                ? 'text-fg-subtle/50'
                : isRowSelected(run.id)
                  ? 'text-primary'
                  : 'text-fg-subtle'
            "
          >
            {{ isRowSelected(run.id) ? 'check_circle' : 'radio_button_unchecked' }}
          </span>

          <div class="flex-1 min-w-0">
            <!-- 行内改名编辑态 -->
            <input
              v-if="editingId === run.id"
              v-model="draftName"
              class="input input-sm w-full"
              :placeholder="run.name ?? '未命名'"
              @keydown.enter="commitRename"
              @keydown.esc="editingId = null"
              @blur="commitRename"
              @click.stop
            />
            <div v-else class="flex items-center gap-2 min-w-0">
              <span
                class="text-sm font-medium truncate"
                :class="isRunSelectable(run.id) ? '' : 'text-fg-subtle'"
              >
                {{ run.name ?? '未命名' }}
              </span>
              <Transition name="pin">
                <span
                  v-if="slotIndex(run.id)"
                  class="text-[10px] px-1.5 py-0.5 rounded-full font-sans shrink-0"
                  :class="
                    slotIndex(run.id) === 1 ? 'bg-primary/15 text-primary' : 'bg-cyan/15 text-cyan'
                  "
                >
                  {{ slotIndex(run.id) === 1 ? '① 基线' : '② 对比' }}
                </span>
              </Transition>
              <button
                class="btn btn-ghost btn-xs p-1 h-6 w-6 shrink-0"
                title="改名"
                @click.stop="startRename(run.id, run.name ?? '')"
              >
                <span class="material-symbols-outlined icon-sm">edit</span>
              </button>
            </div>
          </div>

          <!-- 时间戳：较宽时与名称同行 -->
          <span
            class="text-xs text-fg-subtle font-mono shrink-0 hidden md:inline"
            :class="isRunSelectable(run.id) ? '' : 'opacity-50'"
          >
            {{ formatCreatedAt(run.createdAt) }}
          </span>

          <span
            class="text-xs px-2 py-0.5 rounded-full shrink-0"
            :class="[STATUS_LABEL[run.status]?.cls, isRunSelectable(run.id) ? '' : 'opacity-50']"
          >
            {{ STATUS_LABEL[run.status]?.text }}
          </span>

          <!-- pin 基线（与删除并列在最右侧） -->
          <button
            class="btn btn-ghost btn-xs p-1 h-6 w-6 shrink-0"
            :class="
              slotIndex(run.id) === 1
                ? 'text-primary bg-primary/10'
                : 'text-fg-subtle hover:text-primary'
            "
            :disabled="run.status !== 'SUCCESS'"
            :title="slotIndex(run.id) === 1 ? '取消基线' : '设为基线（对比）'"
            @click.stop="onPinClick(run.id)"
          >
            <span class="material-symbols-outlined icon-sm">push_pin</span>
          </button>

          <!-- 删除运行（所有状态可删，FAIL 行同样可删） -->
          <button
            class="btn btn-ghost btn-xs p-1 h-6 w-6 shrink-0 text-error/70 hover:text-error"
            :disabled="deletingId === run.id"
            title="删除运行"
            @click.stop="handleDeleteRun(run.id)"
          >
            <span v-if="deletingId === run.id" class="loading loading-spinner loading-xs"></span>
            <span v-else class="material-symbols-outlined icon-sm">delete_outline</span>
          </button>
        </div>
      </TransitionGroup>
    </div>

    <!-- 小字说明：可对比性判定依据 -->
    <p class="text-xs text-fg-subtle leading-relaxed">
      可对比性按任务快照一致性判定（依赖可不同，正是对比差异所在）；资源用量、单价、碳因子未纳入快照，若运行间资源侧有变动，结果会失真。
    </p>
  </div>
</template>
