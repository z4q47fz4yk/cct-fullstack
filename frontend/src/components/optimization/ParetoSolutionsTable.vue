<script setup lang="ts">
/**
 * ParetoSolutionsTable - 帕累托最优解宽表格（全宽展示）
 *
 * 取代 ParetoSolutionsList 的卡片列表：
 * - 列：序号 | ID | [来源] | 方案(策略数组 0/1/2/3) | 成本 | 工期 | 碳排 | 峰值人数 | 所需房间数
 * - 排序权重栏（ParetoWeightsBar）内嵌为表格上方的 filter 工具条
 * - 行点击 = 选中解（父组件据此展示甘特图）
 */
import { computed } from 'vue'
import type { ScoredSolution } from '@/utils/paretoScore'
import { fmtInt, fmtNumber, fmtWanYuan } from '@/utils/format'
import ParetoWeightsBar from '@/components/optimization/ParetoWeightsBar.vue'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import LoadingState from '@/components/common/LoadingState.vue'
import { getThemeColors } from '@/utils/themeColors'
import type { NamedWeightPreset, ParetoWeights, WeightPreset } from '@/types/paretoWeights'
import type { TaskMode, TaskWithTagsResp } from '@/client/types.gen'

const selectedId = defineModel<number | null>('selectedId')
const weights = defineModel<ParetoWeights>('weights', { required: true })

const {
  solutions,
  loading = false,
  presets = [],
  customPresets = [],
  tasks = [],
  sourceNames = {},
} = defineProps<{
  solutions: ScoredSolution[]
  loading?: boolean
  /** 内置权重预设（传递给 filter 工具条） */
  presets?: readonly WeightPreset[]
  /** 自定义权重预设（传递给 filter 工具条） */
  customPresets?: readonly NamedWeightPreset[]
  /** 工序列表（用于方案列按工序顺序排列及 hover 提示） */
  tasks?: TaskWithTagsResp[]
  /** 方案所属运行名（solutionId → run.name）；传入时显示「来源」列（多运行合并场景） */
  sourceNames?: Record<number, string>
}>()

const emit = defineEmits<{
  'add-preset': []
  'remove-preset': [id: string, label: string]
}>()

interface TableHeader {
  key: string
  label: string
  width: string
  /** 数字列：表头右对齐（body td 另加 table-num） */
  num?: boolean
}

/** 是否渲染「来源」列（多运行合并场景由父组件传入 sourceNames） */
const hasSource = computed(() => Object.keys(sourceNames).length > 0)

const tableHeaders = computed<TableHeader[]>(() => [
  { key: 'idx', label: '序号', width: 'w-14' },
  { key: 'id', label: 'ID', width: 'w-24' },
  ...(hasSource.value ? [{ key: 'source', label: '来源', width: 'w-40' }] : []),
  { key: 'strategy', label: '方案', width: 'w-80' },
  { key: 'cost', label: '成本', width: 'w-40', num: true },
  { key: 'duration', label: '工期', width: 'w-28', num: true },
  { key: 'emission', label: '碳排', width: 'w-28', num: true },
  { key: 'peak', label: '峰值人数', width: 'w-28', num: true },
  { key: 'rooms', label: '所需房间数', width: 'w-28', num: true },
])

// ──── 方案列：策略数组（0/1/2/3） ────────────────────────────

const MODE_NAMES = ['普通', '加速', '低碳', '加速且低碳'] as const

/** 方案列最多展示的策略色块数，其余折叠为 +N */
const MAX_SEGMENTS_VISIBLE = 12

interface ModeSeg {
  mode: TaskMode
  taskId: number
}

/** 每个解按工序顺序排列的策略段（taskId 顺序与甘特图一致） */
const strategyMap = computed(() => {
  const order = new Map(tasks.map((t, i) => [t.id, i]))
  return new Map<number, ModeSeg[]>(
    solutions.map((item) => [
      item.solution.id,
      item.solution.strategies
        .slice()
        .sort((a, b) => (order.get(a.taskId) ?? Infinity) - (order.get(b.taskId) ?? Infinity))
        .map((s) => ({ mode: s.mode, taskId: s.taskId }) as ModeSeg),
    ]),
  )
})

/** 工序元信息（hover 提示用） */
const taskMeta = computed(() => new Map<number, TaskWithTagsResp>(tasks.map((t) => [t.id, t])))

/** 策略语义色：0=中性 / 1=加速橙 / 2=低碳绿 / 3=双策略紫（与甘特图一致） */
function strategyColor(mode: TaskMode): string {
  const C = getThemeColors()
  switch (mode) {
    case 0:
      return C.label
    case 1:
      return C.accel
    case 2:
      return C.success
    case 3:
      return C.violet
  }
}

function segsOf(id: number): ModeSeg[] {
  return strategyMap.value.get(id) ?? []
}

function visibleSegs(id: number): ModeSeg[] {
  return segsOf(id).slice(0, MAX_SEGMENTS_VISIBLE)
}

function hiddenSegCount(id: number): number {
  return Math.max(0, segsOf(id).length - MAX_SEGMENTS_VISIBLE)
}

function taskLabel(taskId: number): string {
  const t = taskMeta.value.get(taskId)
  return t ? `${t.code} ${t.name}`.trim() : `工序 ${taskId}`
}

function segTitle(id: number, index: number): string {
  const seg = segsOf(id)[index]
  if (!seg) return ''
  return `${taskLabel(seg.taskId)} · ${MODE_NAMES[seg.mode]}`
}

function allSegsTitle(id: number): string {
  return segsOf(id)
    .map((s) => `${taskLabel(s.taskId)}·${s.mode}`)
    .join(' ')
}

function onSelect(id: number) {
  selectedId.value = id
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- 标题行 -->
    <div class="shrink-0 px-4 pt-3 pb-2 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <h2 class="text-base font-semibold text-base-content">帕累托最优解</h2>
        <span class="text-xs text-fg-muted font-mono">{{ solutions.length }} 个解</span>
      </div>
      <div class="flex items-center gap-4">
        <!-- 策略色图例：0 普通 / 1 加速 / 2 低碳 / 3 双策略 -->
        <div class="flex items-center gap-2.5">
          <span
            v-for="(name, mode) in MODE_NAMES"
            :key="mode"
            class="flex items-center gap-1 text-xs text-fg-muted"
            :title="`${mode} · ${name}`"
          >
            <span
              class="w-3 h-3 rounded-[3px] inline-block"
              :style="{ background: strategyColor(mode as TaskMode) }"
            ></span>
            {{ mode }}
          </span>
        </div>
        <span class="text-xs text-fg-subtle">点击行查看甘特图</span>
      </div>
    </div>

    <!-- 排序权重 filter 工具条（内嵌） -->
    <div class="shrink-0 px-4 pb-3">
      <ParetoWeightsBar
        v-model:weights="weights"
        :presets="presets"
        :custom-presets="customPresets"
        bare
        @add-preset="emit('add-preset')"
        @remove-preset="(id, label) => emit('remove-preset', id, label)"
      />
    </div>

    <div class="shrink-0 border-b border-base-content/10" />

    <!-- 表格区 -->
    <div class="flex-1 min-h-0 overflow-y-auto">
      <LoadingState v-if="loading" variant="skeleton" class="p-4">
        <div class="space-y-2">
          <div v-for="i in 6" :key="i" class="skeleton h-10 w-full rounded"></div>
        </div>
      </LoadingState>

      <table v-else class="table table-pin-rows">
        <thead>
          <tr>
            <th v-for="h in tableHeaders" :key="h.key" :class="[h.width, h.num ? 'table-num' : '']">
              {{ h.label }}
            </th>
          </tr>
        </thead>
        <!-- 切换权重排序时，行间 FLIP 平移动画 -->
        <TransitionGroup v-if="solutions.length > 0" tag="tbody" name="flip">
          <tr
            v-for="(item, i) in solutions"
            :key="item.solution.id"
            class="cursor-pointer transition-colors"
            :class="
              selectedId === item.solution.id
                ? 'bg-primary/10 border-l-2 border-l-primary'
                : 'hover:bg-base-300/30'
            "
            role="button"
            tabindex="0"
            :aria-pressed="selectedId === item.solution.id"
            :aria-label="`方案 ${i + 1}，成本 ${item.solution.cost}，工期 ${item.solution.duration} 天`"
            @click="onSelect(item.solution.id)"
            @keydown.enter.prevent="onSelect(item.solution.id)"
            @keydown.space.prevent="onSelect(item.solution.id)"
          >
            <td class="w-14 text-fg-muted font-mono">{{ i + 1 }}</td>
            <td class="w-24 text-fg-muted font-mono">{{ item.solution.id }}</td>
            <td
              v-if="hasSource"
              class="w-40 text-fg-muted font-mono truncate max-w-40"
              :title="sourceNames[item.solution.id]"
            >
              {{ sourceNames[item.solution.id] ?? '—' }}
            </td>
            <!-- 方案：各工序策略数组（0 普通 / 1 加速 / 2 低碳 / 3 双策略） -->
            <td class="w-80">
              <div class="flex items-center gap-1">
                <span
                  v-for="(seg, si) in visibleSegs(item.solution.id)"
                  :key="si"
                  class="w-4 h-4 rounded-[3px] flex items-center justify-center text-[10px] leading-none font-mono text-neutral cursor-default shrink-0"
                  :style="{ background: strategyColor(seg.mode) }"
                  :title="segTitle(item.solution.id, si)"
                >
                  {{ seg.mode }}
                </span>
                <span
                  v-if="hiddenSegCount(item.solution.id) > 0"
                  class="text-xs text-fg-subtle font-mono px-1 cursor-default shrink-0"
                  :title="allSegsTitle(item.solution.id)"
                >
                  +{{ hiddenSegCount(item.solution.id) }}
                </span>
              </div>
            </td>
            <td class="table-num w-40">
              {{ fmtWanYuan(item.solution.cost) }}<span class="text-xs text-fg-subtle">万</span>
            </td>
            <td class="table-num w-28">
              {{ fmtNumber(item.solution.duration, 1) }}
              <span class="text-xs text-fg-subtle">天</span>
            </td>
            <td class="table-num w-28">
              {{ fmtNumber(item.solution.emission / 1000, 2)
              }}<span class="text-xs text-fg-subtle">t</span>
            </td>
            <td class="table-num w-28">
              {{ fmtInt(item.solution.peakPersonnel) }}
              <span class="text-xs text-fg-subtle">人</span>
            </td>
            <td class="table-num w-28">
              {{ fmtInt(item.solution.housingRooms) }}
              <span class="text-xs text-fg-subtle">间</span>
            </td>
          </tr>
        </TransitionGroup>
        <tbody v-else>
          <TableEmptyState
            :colspan="tableHeaders.length"
            icon="scatter_plot"
            title="暂无解集"
            description="请先运行一次优化"
          />
        </tbody>
      </table>
    </div>
  </div>
</template>
