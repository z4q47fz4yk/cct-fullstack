<script setup lang="ts">
/**
 * SchemeCard - 优化方案列表卡片（统一模板）
 *
 * 取代 ParetoSolutionsList 中重复的方案卡片实现。
 * idx 统一为 1-based（用户视角：方案 #1、#2...）。
 */
import type { OptimizeSolution } from '@/client/types.gen'
import { fmtDays, fmtInt, fmtNumber, fmtWanYuan } from '@/utils/format'

interface Props {
  /** 解数据 */
  sol: OptimizeSolution
  /** 显示序号（1-based；父组件传 idx + 1） */
  displayIdx: number
  /** 是否处于选中态 */
  selected?: boolean
  /** 是否禁用（不可点击 / 加入对比） */
  disabled?: boolean
  /** 是否展示「峰值施工人数」（仅方案对比场景用） */
  showPeak?: boolean
  /** 紧凑模式（用于 ParetoSolutionsList 列表） */
  compact?: boolean
  /** 自定义类名（追加到根节点） */
  cardClass?: string
}

const {
  sol,
  displayIdx,
  selected = false,
  disabled = false,
  showPeak = false,
  compact = false,
  cardClass = '',
} = defineProps<Props>()

const emit = defineEmits<{
  /** 点击卡片（用于「选中解并展示详情」） */
  select: [solId: number]
  /** 点击「对比」按钮（用于加入方案对比列表） */
  compare: [solId: number]
}>()

function handleSelect() {
  if (disabled) return
  emit('select', sol.id)
}

function handleCompare(e: MouseEvent) {
  e.stopPropagation()
  if (disabled) return
  emit('compare', sol.id)
}
</script>

<template>
  <div
    class="panel panel-hover cursor-pointer"
    :class="[
      selected ? 'border-2 border-primary' : 'border border-transparent hover:border-primary/30',
      disabled ? 'opacity-50 cursor-not-allowed' : '',
      cardClass,
    ]"
    role="button"
    :aria-pressed="selected"
    :aria-disabled="disabled"
    :aria-label="`方案 ${displayIdx}，成本 ${sol.cost}，工期 ${sol.duration} 天`"
    @click="handleSelect"
    @keydown.enter="handleSelect"
    @keydown.space.prevent="handleSelect"
  >
    <div :class="[compact ? 'p-3' : 'p-4']">
      <div class="flex items-center justify-between mb-2">
        <h4 class="font-semibold text-base-content">方案 #{{ displayIdx }}</h4>
        <span v-if="selected" class="badge badge-primary badge-sm">已选中</span>
      </div>

      <div :class="['grid gap-3', showPeak ? 'grid-cols-4' : 'grid-cols-3']">
        <div>
          <p class="text-xs text-fg-muted">成本</p>
          <p class="text-lg font-semibold font-num text-primary truncate">
            {{ fmtWanYuan(sol.cost) }}
          </p>
        </div>
        <div>
          <p class="text-xs text-fg-muted">工期</p>
          <p class="text-lg font-semibold font-num text-info truncate">
            {{ fmtDays(sol.duration) }}
          </p>
        </div>
        <div>
          <p class="text-xs text-fg-muted">碳排</p>
          <p class="text-lg font-semibold font-num text-success truncate">
            {{ fmtNumber(sol.emission / 1000, 2) }}<span class="text-xs font-normal">t</span>
          </p>
        </div>
        <div v-if="showPeak">
          <p class="text-xs text-fg-muted">峰值</p>
          <p class="text-lg font-semibold font-num text-neutral-content truncate">
            {{
              sol.peakPersonnel !== null && sol.peakPersonnel !== undefined
                ? fmtInt(sol.peakPersonnel)
                : '—'
            }}
          </p>
        </div>
      </div>

      <!-- 操作区（对比按钮独立，避免嵌套 button） -->
      <div v-if="!compact" class="card-actions justify-end mt-3">
        <button
          type="button"
          class="btn btn-sm btn-ghost min-h-8 px-3"
          :disabled="disabled"
          :aria-label="`将方案 ${displayIdx} 加入对比`"
          @click="handleCompare"
        >
          <span class="material-symbols-outlined icon-sm">compare_arrows</span>
          加入对比
        </button>
      </div>
    </div>
  </div>
</template>
