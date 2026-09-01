<script setup lang="ts">
/**
 * DailyReportBatchCard - 录入 tab 的「待提交日报批次」摘要卡
 *
 * 读取日报 store（stores/report.ts）的已分配批次状态：
 * - batchId 存在且 resourceUsages > 0（phase ≥ ALLOCATING）时展示
 * - 汇总展示：解析资源数 / 分配工序数 / 分配项数
 * - 复用 AllocationByTask（disable-action 只读）与 AllocationByResource 汇总视图
 * - 提供「移除批次」危险操作（store.reset()）
 *
 * 注意：此组件是日报模块的展示组件，允许直接读取日报 store；
 * 手动录入的待提交行由 ManualUsageByTask 管理（两者解耦）。
 */
import { computed, ref } from 'vue'
import { useConfirm } from '@/composables/useConfirm'
import { useDailyReportStoreV2 } from '@/stores/report'
import AllocationByTask from '@/components/daily-report/AllocationByTask.vue'
import AllocationByResource from '@/components/daily-report/AllocationByResource.vue'

const store = useDailyReportStoreV2()
const { confirmDanger } = useConfirm()

const activeView = ref<'task' | 'resource'>('task')

/** 是否展示：存在已解析批次且已分配资源 */
const hasPendingBatch = computed(() => !!store.batchId && store.resourceUsages.length > 0)

/** 短批次号（UUID 前 8 位） */
const shortBatchId = computed(() => (store.batchId ? store.batchId.slice(0, 8) : ''))

/** 解析资源项数（含 SKIP 前的全部解析项） */
const parsedCount = computed(() => store.parsedResourceItems.length)

/** 分配工序数 / 分配项数 */
const allocatedTaskCount = computed(() => new Set(store.resourceUsages.map((u) => u.taskId)).size)
const allocatedItemCount = computed(() => store.resourceUsages.length)

async function handleRemoveBatch() {
  const r = await confirmDanger(
    '确定要移除这个待提交的日报批次吗？已解析的资源映射与分配数据将一并清除，需重新导入。',
  )
  if (r.confirmed) store.reset()
}
</script>

<template>
  <div v-if="hasPendingBatch" class="panel p-0">
    <div class="px-5 py-3 border-b border-base-content/10 flex flex-wrap items-center gap-3">
      <h3 class="text-sm font-semibold text-base-content flex items-center gap-2">
        <span class="material-symbols-outlined icon-sm text-fg-muted">upload_file</span>
        待提交日报批次
        <span class="badge badge-sm badge-neutral">日报导入</span>
        <span class="text-xs text-fg-subtle font-mono">#{{ shortBatchId }}</span>
      </h3>
      <div class="flex items-center gap-2 ml-auto">
        <span class="badge badge-sm">解析 {{ parsedCount }} 项</span>
        <span class="badge badge-sm">工序 {{ allocatedTaskCount }}</span>
        <span class="badge badge-sm">分配 {{ allocatedItemCount }} 项</span>
        <button class="btn btn-ghost btn-sm text-error" @click="handleRemoveBatch">
          <span class="material-symbols-outlined icon-sm">delete_sweep</span>
          移除批次
        </button>
      </div>
    </div>

    <div class="p-4 space-y-3">
      <div class="join grid grid-cols-2 w-72">
        <button
          type="button"
          class="join-item btn btn-sm"
          :class="activeView === 'task' ? 'btn-primary' : 'btn-outline'"
          @click="activeView = 'task'"
        >
          <span class="material-symbols-outlined icon-sm">construction</span>
          按工序汇总
        </button>
        <button
          type="button"
          class="join-item btn btn-sm"
          :class="activeView === 'resource' ? 'btn-primary' : 'btn-outline'"
          @click="activeView = 'resource'"
        >
          <span class="material-symbols-outlined icon-sm">inventory_2</span>
          按资源汇总
        </button>
      </div>

      <AllocationByTask v-if="activeView === 'task'" disable-action />
      <AllocationByResource v-else />
    </div>
  </div>
</template>
