<script setup lang="ts">
/**
 * ResourceUsageBatchDetail - 单个 batch 的详情面板
 *
 * 复用 ResourceUsageHistoryTable 展示该 batch 的记录
 * 顶部展示 batch 元信息（日期、记录数、来源）
 *
 * batchKey 类型为 string | number：
 * - manual batch 用 manualBatchId（number）
 * - 日报 batch 用 batchId（string UUID）
 */
import { computed } from 'vue'
import type { ResourceUsageResp } from '@/client/types.gen'
import type { ResourceUsageUpdate } from '@/client/types.gen'
import ResourceUsageHistoryTable from './ResourceUsageHistoryTable.vue'

const {
  batchKey,
  records,
  loading = false,
} = defineProps<{
  /** 复合 key：manualBatchId (number) 或 batchId (string) */
  batchKey: string | number
  records: ResourceUsageResp[]
  loading?: boolean
}>()

const emit = defineEmits<{
  close: []
  'update-record': [id: number, data: ResourceUsageUpdate]
  'delete-record': [id: number]
  'delete-batch': []
  tags: [usage: ResourceUsageResp]
}>()

const source = computed<'manual' | 'daily-report' | 'unknown'>(() => {
  if (records.some((r) => r.manualBatchId != null)) return 'manual'
  if (records.some((r) => r.batchId != null)) return 'daily-report'
  return 'unknown'
})

/** 组内记录的类型口径（取首条；同一批次通常统一） */
const usageType = computed<'ACTUAL' | 'PLANNED' | null>(() => records[0]?.usageType ?? null)

const usageTypeLabel = computed(() => {
  if (usageType.value === 'ACTUAL') return '实际'
  if (usageType.value === 'PLANNED') return '计划'
  return ''
})

const usageTypeBadgeClass = computed(() => {
  if (usageType.value === 'ACTUAL') return 'badge-success'
  if (usageType.value === 'PLANNED') return 'badge-warning'
  return 'badge-ghost'
})

const usageDate = computed(() => {
  if (records.length === 0) return ''
  return records[0]?.usageDate ?? ''
})

const batchLabel = computed(() => {
  const r = records[0]
  if (!r) return ''
  // 缩短手动批次 ID 显示，避免大整数影响阅读；title 属性保留完整 ID 便于悬停查看
  if (source.value === 'manual') return `#${String(r.manualBatchId).slice(-6)}`
  if (source.value === 'daily-report' && r.batchId) return r.batchId.slice(0, 8) + '...'
  return ''
})
</script>

<template>
  <div class="p-4 panel">
    <div class="px-5 py-4 border-b border-base-content/10 flex flex-wrap items-center gap-4">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-fg-muted">folder_open</span>
        <h3 class="font-semibold text-base-content">批次详情</h3>
      </div>
      <div class="flex flex-wrap items-center gap-3 text-sm">
        <span class="badge badge-sm badge-neutral">日期 {{ usageDate.slice(0, 10) }}</span>
        <span class="badge badge-sm badge-primary">{{ records.length }} 条记录</span>
        <span class="badge badge-sm" :class="source === 'manual' ? 'badge-info' : 'badge-neutral'">
          {{
            source === 'manual' ? '手动录入' : source === 'daily-report' ? '日报导入' : '未知来源'
          }}
        </span>
        <span v-if="usageType" class="badge badge-sm" :class="usageTypeBadgeClass">
          {{ usageTypeLabel }}口径
        </span>
        <span v-if="batchLabel" class="text-xs text-fg-subtle font-mono">{{ batchLabel }}</span>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <button
          class="btn btn-ghost btn-sm text-error"
          :disabled="loading"
          @click="emit('delete-batch')"
        >
          <span class="material-symbols-outlined icon-sm">delete_sweep</span>
          删除整批
        </button>
        <button class="btn btn-ghost btn-sm btn-square" title="关闭" @click="emit('close')">
          <span class="material-symbols-outlined icon-sm">close</span>
        </button>
      </div>
    </div>

    <div class="p-4">
      <ResourceUsageHistoryTable
        :records="records"
        :loading="loading"
        @delete="(id) => emit('delete-record', id)"
        @update="(id, data) => emit('update-record', id, data)"
        @tags="(usage) => emit('tags', usage)"
      />
    </div>
  </div>
</template>
