<script setup lang="ts">
/**
 * 资源使用量 - 历史批次（默认子页）
 *
 * 展示全部来源（手动/日报）批次，带用量类型徽标；
 * 支持筛选、批次详情、删除/更新、用量/批次打标。
 */
import { computed, ref } from 'vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ResourceUsageBatchList from '@/components/resource-usage/ResourceUsageBatchList.vue'
import ResourceUsageBatchDetail from '@/components/resource-usage/ResourceUsageBatchDetail.vue'
import ResourceUsageFilters from '@/components/resource-usage/ResourceUsageFilters.vue'
import TagAssignModal from '@/components/tag/TagAssignModal.vue'
import {
  useResourceUsageApi,
  getUsageChunkKey,
  type ResourceUsageFilters as Filters,
} from '@/composables/useResourceUsageApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { daysAgoIsoLocal, todayIsoLocal } from '@/utils/date'

import type { TagEntityRef } from '@/composables/useEntityTagApi'
import type {
  ResourceUsageResp,
  ResourceUsageUpdate,
  ResourceUsageWithTagsResp,
  TagResp,
} from '@/client/types.gen'

definePage({
  meta: {
    title: '历史',
    description: '查看全部手动/日报使用量批次',
    icon: 'history',
    showInNav: true,
    parentName: '/project/[projectId]/resource-usage',
    navOrder: 1,
  },
})

const { currentProjectId } = useProjectContext()

// 筛选：进入页面默认查询最近 3 天（含今天），可清空/改范围
const filters = ref<Filters>({
  dateFrom: daysAgoIsoLocal(2),
  dateTo: todayIsoLocal(),
})

const { usages, isLoading, error, refresh, updateUsage, deleteUsage, deleteBatch } =
  useResourceUsageApi({ filters })

// 当前正在查看详情的分块复合 key：(usage-date, batch-id)
const viewingChunkKey = ref<string | null>(null)
const viewingBatchRecords = computed<ResourceUsageResp[]>(() => {
  if (viewingChunkKey.value === null) return []
  return usages.value.filter((u) => getUsageChunkKey(u) === viewingChunkKey.value)
})

function openBatchDetail(chunkKey: string) {
  viewingChunkKey.value = chunkKey
}
function closeBatchDetail() {
  viewingChunkKey.value = null
}

// ─── 记录 / 批次操作 ──────────────────────────────────────

async function handleDeleteRecord(id: number) {
  try {
    await deleteUsage({ path: { project_id: currentProjectId.value!, id } })
    await refresh()
    if (viewingChunkKey.value !== null && viewingBatchRecords.value.length === 0) {
      closeBatchDetail()
    }
  } catch (e) {
    console.error('Delete record failed:', e)
  }
}

async function handleUpdateRecord(id: number, data: ResourceUsageUpdate) {
  try {
    await updateUsage({ path: { project_id: currentProjectId.value!, id }, body: data })
    await refresh()
  } catch (e) {
    console.error('Update record failed:', e)
  }
}

async function handleDeleteBatch(chunkKey: string, records: ResourceUsageResp[]) {
  try {
    await deleteBatch(records)
    if (viewingChunkKey.value === chunkKey) closeBatchDetail()
    await refresh()
  } catch (e) {
    console.error('Delete batch failed:', e)
  }
}

// ─── 用量打标（USAGE 切片实体，导入后的用量也可补标） ──────
const showUsageTagModal = ref(false)
const taggingUsage = ref<ResourceUsageResp | null>(null)
const taggingUsageName = computed(() => {
  if (!taggingUsage.value) return '用量'
  return `用量 #${taggingUsage.value.id}`
})

function openUsageTags(usage: ResourceUsageResp) {
  taggingUsage.value = usage
  showUsageTagModal.value = true
}

// ─── 批次打标（整批记录应用同一组标签） ─────────────────────
const showBatchTagModal = ref(false)
const taggingBatchRecords = ref<ResourceUsageWithTagsResp[]>([])

function openBatchTags(records: ResourceUsageWithTagsResp[]) {
  taggingBatchRecords.value = records
  showBatchTagModal.value = true
}

const taggingBatchName = computed(() => {
  const count = taggingBatchRecords.value.length
  return count > 0 ? `用量批次（${count} 条记录）` : '用量批次'
})

/** 批量打标目标实体：批次内每条记录 */
const taggingBatchEntities = computed<TagEntityRef[]>(() =>
  taggingBatchRecords.value.map((r) => ({ type: 'usage', id: r.id })),
)

/** 批量模式初始标签：批次内所有记录当前标签的并集 */
const taggingBatchInitialTags = computed<TagResp[]>(() => {
  const map = new Map<number, TagResp>()
  for (const r of taggingBatchRecords.value) {
    for (const t of r.tags ?? []) {
      if (!map.has(t.id)) map.set(t.id, t)
    }
  }
  return Array.from(map.values())
})
</script>

<template>
  <ErrorState
    v-if="error"
    title="加载失败"
    description="无法获取使用量记录，请检查网络连接"
    class="mb-4"
    @retry="refresh"
  />

  <ResourceUsageFilters v-model:filters="filters" />

  <ResourceUsageBatchList
    class="panel p-0"
    v-if="viewingChunkKey === null"
    :usages="usages"
    :loading="isLoading"
    @view-detail="openBatchDetail"
    @delete-batch="handleDeleteBatch"
    @tags-batch="openBatchTags"
  />

  <ResourceUsageBatchDetail
    v-else
    :chunk-key="viewingChunkKey"
    :records="viewingBatchRecords"
    :loading="isLoading"
    @close="closeBatchDetail"
    @update-record="handleUpdateRecord"
    @delete-record="handleDeleteRecord"
    @delete-batch="handleDeleteBatch(viewingChunkKey!, viewingBatchRecords)"
    @tags="openUsageTags"
  />

  <!-- 用量打标模态框 -->
  <TagAssignModal
    :show="showUsageTagModal"
    :entity="taggingUsage ? { type: 'usage', id: taggingUsage.id } : null"
    :entity-name="taggingUsageName"
    @saved="showUsageTagModal = false"
    @cancel="showUsageTagModal = false"
  />

  <!-- 批次打标模态框 -->
  <TagAssignModal
    :show="showBatchTagModal"
    :entity="null"
    :entities="taggingBatchEntities"
    :initial-tags="taggingBatchInitialTags"
    :entity-name="taggingBatchName"
    @saved="showBatchTagModal = false"
    @cancel="showBatchTagModal = false"
  />
</template>
