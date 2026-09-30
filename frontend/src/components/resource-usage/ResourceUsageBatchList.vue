<script setup lang="ts">
/**
 * ResourceUsageBatchList - 历史 tab 的批次分块列表
 *
 * 按 (usage-date, batch-id) 复合分块，每行展示一个分块：
 * - 日期（usageDate）
 * - 记录数
 * - 来源（手动 / 日报）
 * - 备注（手动批次取 manualBatch.name；日报导入为空）
 * - 操作：查看详情、删除分块记录
 *
 * 分块键：手动 batch 用 manualBatchId (number)，日报 batch 用 batchId (string)，
 * 与 usageDate 拼接成复合 chunkKey；同一批次含多天记录时会显示为多行。
 *
 * 支持列排序（使用日期/记录数/来源/备注/批次）与前端分页（后端列表接口不分页，E-11）；
 * 批次详情以「展开行」形式嵌在对应行下方，与列表并存（E-6）。
 */
import { computed, ref, watch } from 'vue'
import type { ResourceUsageWithTagsResp, TagResp } from '@/client/types.gen'
import { getUsageBatchId, getUsageChunkKey } from '@/composables/useResourceUsageApi'
import { useConfirm } from '@/composables/useConfirm'
import { getSliceColor } from '@/utils/themeColors'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import PaginationBar from '@/components/common/PaginationBar.vue'

const {
  usages,
  loading = false,
  activeChunkKey = null,
} = defineProps<{
  usages: ResourceUsageWithTagsResp[]
  loading?: boolean
  /** 当前展开详情的分块 key（展开行高亮 + 插槽渲染位置） */
  activeChunkKey?: string | null
}>()

const emit = defineEmits<{
  /** 点击「查看详情 / 收起详情」（切换语义） */
  'view-detail': [chunkKey: string]
  /** 详情行已不在当前页等场景下请求父组件关闭详情 */
  'close-detail': []
  /** 删除该分块（同一 batch 的其它日期分块不受影响） */
  'delete-batch': [chunkKey: string, records: ResourceUsageWithTagsResp[]]
  /** 为整个 batch 打标 */
  'tags-batch': [records: ResourceUsageWithTagsResp[]]
}>()

const { confirmDanger } = useConfirm()

interface BatchGroup {
  /** 复合键：`${usageDate}|${batchId}`（manualBatchId 或 batchId） */
  chunkKey: string
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
    const chunkKey = getUsageChunkKey(u)
    if (chunkKey === null) continue
    const rawId = getUsageBatchId(u)
    if (rawId === null) continue
    if (!map.has(chunkKey)) {
      map.set(chunkKey, {
        chunkKey,
        rawId,
        usageDate: (u.usageDate ?? '').slice(0, 10),
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
    const g = map.get(chunkKey)!
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
  const r = await confirmDanger(`确定要删除该分块（${group.count} 条记录）吗？此操作不可恢复。`)
  if (r.confirmed) emit('delete-batch', group.chunkKey, group.records)
}

// ─── 排序（E-11）：后端列表接口不分页/无 sort 参数，对已加载分块前端排序 ───

type SortKey = 'usageDate' | 'count' | 'source' | 'remark' | 'rawId'

const sortKey = ref<SortKey>('usageDate')
const sortDir = ref<'asc' | 'desc'>('desc')

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    // 日期默认新→旧；其余列默认小→大
    sortDir.value = key === 'usageDate' ? 'desc' : 'asc'
  }
}

function compareGroups(a: BatchGroup, b: BatchGroup): number {
  switch (sortKey.value) {
    case 'usageDate': {
      if (a.usageDate !== b.usageDate) return a.usageDate < b.usageDate ? -1 : 1
      // 同日期按创建时间新→旧（与默认顺序一致）
      return a.latestCreatedAt < b.latestCreatedAt
        ? 1
        : a.latestCreatedAt > b.latestCreatedAt
          ? -1
          : 0
    }
    case 'count':
      return a.count - b.count
    case 'source':
      return sourceLabel(a.source).localeCompare(sourceLabel(b.source), 'zh-CN')
    case 'remark':
      return a.remark.localeCompare(b.remark, 'zh-CN')
    case 'rawId':
      return String(a.rawId).localeCompare(String(b.rawId), 'zh-CN', { numeric: true })
  }
}

const sortedGroups = computed<BatchGroup[]>(() => {
  const sign = sortDir.value === 'asc' ? 1 : -1
  return [...groups.value].sort((a, b) => compareGroups(a, b) * sign)
})

// ─── 分页（E-11）：前端对已加载分块分页，复用 PaginationBar ──────────

const page = ref(1)
const pageSize = ref(10)

const pagedGroups = computed<BatchGroup[]>(() => {
  const start = (page.value - 1) * pageSize.value
  return sortedGroups.value.slice(start, start + pageSize.value)
})

// 数据变化 / 每页条数调整后，页码越界时回夹取到末页
watch([sortedGroups, pageSize], () => {
  const totalPages = Math.max(1, Math.ceil(sortedGroups.value.length / pageSize.value))
  if (page.value > totalPages) page.value = totalPages
})

// 详情行已不在当前页时请求父组件关闭（避免孤儿状态）
watch(pagedGroups, (list) => {
  if (activeChunkKey != null && !list.some((g) => g.chunkKey === activeChunkKey)) {
    emit('close-detail')
  }
})

interface TableHeader {
  key: string
  label: string
  width: string
  /** 可排序列对应的排序键（tags/actions 不可排序） */
  sortKey?: SortKey
  num?: boolean
}

const tableHeaders: TableHeader[] = [
  { key: 'date', label: '使用日期', width: 'w-32', sortKey: 'usageDate' },
  { key: 'count', label: '记录数', width: 'w-24', sortKey: 'count', num: true },
  { key: 'source', label: '来源', width: 'w-32', sortKey: 'source' },
  { key: 'remark', label: '备注', width: 'flex-1', sortKey: 'remark' },
  { key: 'tags', label: '标签', width: 'w-52' },
  { key: 'batch', label: '批次', width: 'w-32', sortKey: 'rawId' },
  { key: 'actions', label: '操作', width: 'w-56' },
]
</script>

<template>
  <div class="">
    <div class="">
      <table class="table">
        <thead>
          <tr>
            <!-- 可排序列头（E-11）：点击循环 升序/降序 -->
            <th
              v-for="h in tableHeaders"
              :key="h.key"
              :class="[h.width, h.num ? 'table-num' : '']"
              :aria-sort="
                h.sortKey && h.sortKey === sortKey
                  ? sortDir === 'asc'
                    ? 'ascending'
                    : 'descending'
                  : undefined
              "
            >
              <button
                v-if="h.sortKey"
                type="button"
                class="inline-flex items-center gap-0.5"
                :title="`按${h.label}排序`"
                @click="toggleSort(h.sortKey)"
              >
                {{ h.label }}
                <span
                  class="material-symbols-outlined icon-sm"
                  :class="h.sortKey === sortKey ? 'text-primary' : 'text-fg-subtle opacity-40'"
                >
                  {{
                    h.sortKey === sortKey
                      ? sortDir === 'asc'
                        ? 'arrow_upward'
                        : 'arrow_downward'
                      : 'unfold_more'
                  }}
                </span>
              </button>
              <template v-else>{{ h.label }}</template>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="pagedGroups.length > 0">
            <template v-for="g in pagedGroups" :key="g.chunkKey">
              <tr
                class="hover:bg-base-content/5 transition-colors"
                :class="activeChunkKey === g.chunkKey ? 'bg-primary/5' : ''"
              >
                <td>{{ formatDate(g.usageDate) }}</td>
                <td class="table-num">
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
                      :title="activeChunkKey === g.chunkKey ? '收起详情' : '查看详情'"
                      @click="emit('view-detail', g.chunkKey)"
                    >
                      <span class="material-symbols-outlined icon-sm">
                        {{ activeChunkKey === g.chunkKey ? 'collapse_all' : 'visibility' }}
                      </span>
                    </button>
                    <button
                      class="btn btn-ghost btn-xs btn-square text-error hover:bg-error/10"
                      title="删除该分块记录"
                      @click="handleDelete(g)"
                    >
                      <span class="material-symbols-outlined icon-sm">delete_sweep</span>
                    </button>
                  </div>
                </td>
              </tr>
              <!-- 展开行：批次详情与列表并存，可收起/关闭（E-6） -->
              <tr v-if="activeChunkKey === g.chunkKey" class="bg-base-200/30">
                <td :colspan="tableHeaders.length" class="p-4">
                  <slot name="detail" />
                </td>
              </tr>
            </template>
          </template>
          <TableEmptyState
            v-else
            :colspan="tableHeaders.length"
            title="暂无录入批次"
            description="到左侧导航「录入」页面添加第一条记录"
            icon="inventory_2"
          />
        </tbody>
      </table>

      <!-- 前端分页（后端列表接口不分页，E-11） -->
      <div v-if="groups.length > 0" class="border-t border-base-content/10">
        <PaginationBar
          v-model:current="page"
          v-model:page-size="pageSize"
          :total="sortedGroups.length"
        />
      </div>
    </div>
  </div>
</template>
