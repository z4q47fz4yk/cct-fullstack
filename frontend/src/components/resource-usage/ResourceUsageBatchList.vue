<script setup lang="ts">
/**
 * ResourceUsageBatchList - 历史 tab 的 batch 列表
 *
 * 按 batchId 分组，每行展示一个 batch：
 * - 日期（usageDate）
 * - 记录数
 * - 来源（手动 / 日报）
 * - 备注（手动批次取 manualBatch.name；日报导入为空）
 * - 操作：查看详情、删除整 batch
 *
 * 分组键：手动 batch 用 manualBatchId (number)，日报 batch 用 batchId (string)
 * 互斥；同一行记录只会落入其中一种
 */
import { computed } from 'vue'
import type { ResourceUsageWithTagsResp, TagResp } from '@/client/types.gen'
import { useConfirm } from '@/composables/useConfirm'
import { getSliceColor } from '@/utils/themeColors'
import TableEmptyState from '@/components/common/TableEmptyState.vue'

const { usages, loading = false } = defineProps<{
  usages: ResourceUsageWithTagsResp[]
  loading?: boolean
}>()

const emit = defineEmits<{
  /** 点击「查看详情」 */
  'view-detail': [batchKey: string | number]
  /** 删除整个 batch */
  'delete-batch': [batchKey: string | number, records: ResourceUsageWithTagsResp[]]
  /** 为整个 batch 打标 */
  'tags-batch': [records: ResourceUsageWithTagsResp[]]
}>()

const { confirmDanger } = useConfirm()

interface BatchGroup {
  /** 复合 id：manualBatchId (number) 或 batchId (string) */
  batchKey: string | number
  /** 原始 id（number for manual, string for daily-report） */
  rawId: string | number
  usageDate: string
  count: number
  latestCreatedAt: string
  /** 备注（手动批次取 manualBatch.name；日报导入为空） */
  remark: string
  records: ResourceUsageWithTagsResp[]
  source: 'manual' | 'daily-report' | 'unknown'
  /** 组内记录的类型口径（同一批次通常统一；取首条） */
  usageType: 'ACTUAL' | 'PLANNED' | null
  /** 组内所有记录的标签并集（按 tag.id 去重） */
  tags: TagResp[]
}

/** 聚合 batch 内所有记录的标签，按 id 去重 */
function groupTags(records: ResourceUsageWithTagsResp[]): TagResp[] {
  const map = new Map<number, TagResp>()
  for (const r of records) {
    for (const t of r.tags ?? []) {
      if (!map.has(t.id)) map.set(t.id, t)
    }
  }
  return Array.from(map.values())
}

const MAX_TAGS_VISIBLE = 2

function visibleTags(group: BatchGroup) {
  return group.tags.slice(0, MAX_TAGS_VISIBLE)
}

function hiddenTagCount(group: BatchGroup): number {
  return Math.max(0, group.tags.length - MAX_TAGS_VISIBLE)
}

function tagListText(group: BatchGroup): string {
  return group.tags.map((t) => t.name).join('、')
}

const groups = computed<BatchGroup[]>(() => {
  const map = new Map<string, BatchGroup>()
  for (const u of usages) {
    // 同一记录仅取其中一个字段（互斥）
    const rawId: string | number | null =
      u.manualBatchId !== null && u.manualBatchId !== undefined
        ? u.manualBatchId
        : u.batchId !== null && u.batchId !== undefined
          ? u.batchId
          : null
    if (rawId === null) continue
    const key = String(rawId)
    if (!map.has(key)) {
      map.set(key, {
        batchKey: rawId,
        rawId,
        usageDate: u.usageDate,
        count: 0,
        latestCreatedAt: u.createdAt,
        remark: u.manualBatch?.name ?? '',
        records: [],
        source:
          u.manualBatchId !== null && u.manualBatchId !== undefined ? 'manual' : 'daily-report',
        usageType: u.usageType ?? null,
        tags: [],
      })
    }
    const g = map.get(key)!
    g.count += 1
    g.records.push(u)
    if (u.createdAt > g.latestCreatedAt) g.latestCreatedAt = u.createdAt
  }
  const result = Array.from(map.values()).sort((a, b) => {
    if (a.usageDate !== b.usageDate) return a.usageDate < b.usageDate ? 1 : -1
    return a.latestCreatedAt < b.latestCreatedAt ? 1 : -1
  })
  for (const g of result) g.tags = groupTags(g.records)
  return result
})

function formatDate(iso: string) {
  return iso.slice(0, 10)
}
function sourceLabel(s: BatchGroup['source']) {
  if (s === 'manual') return '手动录入'
  if (s === 'daily-report') return '日报导入'
  return '未知来源'
}
function sourceBadgeClass(s: BatchGroup['source']) {
  if (s === 'manual') return 'badge-info'
  if (s === 'daily-report') return 'badge-neutral'
  return 'badge-ghost'
}
function usageTypeLabel(t: BatchGroup['usageType']) {
  if (t === 'ACTUAL') return '实际'
  if (t === 'PLANNED') return '计划'
  return ''
}
function usageTypeBadgeClass(t: BatchGroup['usageType']) {
  if (t === 'ACTUAL') return 'badge-success'
  if (t === 'PLANNED') return 'badge-warning'
  return 'badge-ghost'
}
function batchLabel(g: BatchGroup) {
  // 缩短手动批次 ID 显示，避免大整数影响阅读；title 属性保留完整 ID 便于悬停查看
  if (g.source === 'manual') return `#${String(g.rawId).slice(-6)}`
  return String(g.rawId).slice(0, 8) + '...'
}

async function handleDelete(group: BatchGroup) {
  const r = await confirmDanger(`确定要删除该批次（${group.count} 条记录）吗？此操作不可恢复。`)
  if (r.confirmed) emit('delete-batch', group.batchKey, group.records)
}

const tableHeaders = [
  { key: 'date', label: '使用日期', width: 'w-32' },
  { key: 'count', label: '记录数', width: 'w-24' },
  { key: 'source', label: '来源', width: 'w-32' },
  { key: 'remark', label: '备注', width: 'flex-1' },
  { key: 'tags', label: '标签', width: 'w-52' },
  { key: 'batch', label: '批次', width: 'w-32' },
  { key: 'actions', label: '操作', width: 'w-56' },
]
</script>

<template>
  <div class="">
    <div class="">
      <table class="table">
        <thead>
          <tr>
            <th v-for="h in tableHeaders" :key="h.key" :class="[h.width]">
              {{ h.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="groups.length > 0">
            <tr
              v-for="g in groups"
              :key="String(g.batchKey)"
              class="hover:bg-base-content/5 transition-colors"
            >
              <td>{{ formatDate(g.usageDate) }}</td>
              <td>
                <span class="badge badge-sm badge-primary">{{ g.count }} 条</span>
              </td>
              <td>
                <span class="flex items-center gap-1">
                  <span class="badge badge-sm" :class="sourceBadgeClass(g.source)">
                    {{ sourceLabel(g.source) }}
                  </span>
                  <span
                    v-if="g.usageType"
                    class="badge badge-sm"
                    :class="usageTypeBadgeClass(g.usageType)"
                  >
                    {{ usageTypeLabel(g.usageType) }}
                  </span>
                </span>
              </td>
              <td>
                <span v-if="g.remark" class="text-sm text-base-content/80">{{ g.remark }}</span>
                <span v-else class="text-sm text-fg-muted">—</span>
              </td>
              <td>
                <!-- 标签列：组内记录标签并集，超限折叠为 +N，悬浮查看全量 -->
                <div
                  v-if="g.tags.length > 0"
                  class="flex items-center gap-1 overflow-hidden"
                  :title="tagListText(g)"
                >
                  <span
                    v-for="(tag, index) in visibleTags(g)"
                    :key="tag.id"
                    class="inline-flex items-center gap-1 h-5 px-1.5 rounded-full border text-[10px] whitespace-nowrap shrink-0"
                    :style="{
                      backgroundColor: `${getSliceColor(index)}14`,
                      borderColor: `${getSliceColor(index)}3d`,
                    }"
                  >
                    <span
                      class="w-1.5 h-1.5 rounded-full shrink-0"
                      :style="{ backgroundColor: getSliceColor(index) }"
                    ></span>
                    <span class="text-fg-muted">{{ tag.name }}</span>
                  </span>
                  <span
                    v-if="hiddenTagCount(g) > 0"
                    class="inline-flex items-center h-5 px-1.5 rounded-full border border-base-content/20 bg-base-200/60 text-[10px] font-mono text-fg-subtle whitespace-nowrap shrink-0"
                  >
                    +{{ hiddenTagCount(g) }}
                  </span>
                </div>
                <span v-else class="text-xs text-fg-subtle">未打标</span>
              </td>
              <td>
                <span class="font-mono text-xs text-base-content/70" :title="String(g.rawId)">
                  {{ batchLabel(g) }}
                </span>
              </td>
              <td>
                <div class="flex items-center gap-1">
                  <button
                    class="btn btn-ghost btn-xs btn-square"
                    title="为整批打标"
                    @click="emit('tags-batch', g.records)"
                  >
                    <span class="material-symbols-outlined icon-sm">label</span>
                  </button>
                  <button
                    class="btn btn-ghost btn-xs btn-square"
                    title="查看详情"
                    @click="emit('view-detail', g.batchKey)"
                  >
                    <span class="material-symbols-outlined icon-sm">visibility</span>
                  </button>
                  <button
                    class="btn btn-ghost btn-xs btn-square text-error hover:bg-error/10"
                    title="删除整批"
                    @click="handleDelete(g)"
                  >
                    <span class="material-symbols-outlined icon-sm">delete_sweep</span>
                  </button>
                </div>
              </td>
            </tr>
          </template>
          <TableEmptyState
            v-else
            :colspan="tableHeaders.length"
            title="暂无录入批次"
            description="切换到「录入」标签添加第一条记录"
            icon="inventory_2"
          />
        </tbody>
      </table>
    </div>
  </div>
</template>
