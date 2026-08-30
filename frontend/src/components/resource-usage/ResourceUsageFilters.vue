<script setup lang="ts">
/**
 * ResourceUsageFilters - 历史 tab 筛选器
 *
 * 字段：日期范围（from/to）、任务多选、资源多选、批次 ID
 * 通过 v-model 双向绑定到父组件的 filters ref
 */
import { computed, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { useQuery } from '@pinia/colada'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useProjectContext } from '@/composables/useProjectContext'
import { useScheduleApi } from '@/composables/useScheduleApi'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import SegmentControl, { type SegmentOption } from '@/components/common/SegmentControl.vue'
import type {
  ResourceUsageFilters,
  ResourceUsageFilterUsageType,
} from '@/composables/useResourceUsageApi'
import type { UsageType } from '@/client/types.gen'

const filters = defineModel<ResourceUsageFilters>('filters', { required: true })

const { currentProjectId } = useProjectContext()
const { tasks } = useScheduleApi()

// 资源搜索
const searchKeyword = ref('')
const debouncedSearch = ref('')
const updateDebouncedSearch = useDebounceFn((v: string) => {
  debouncedSearch.value = v
}, 300)
watch(searchKeyword, (v) => updateDebouncedSearch(v))

const { state: resourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { name: debouncedSearch.value || undefined, per_page: FETCH_ALL_PAGE_SIZE },
  }),
)
const allResources = computed(() => resourcesState.value?.data?.items ?? [])

function setFilter<K extends keyof ResourceUsageFilters>(key: K, val: ResourceUsageFilters[K]) {
  filters.value = { ...filters.value, [key]: val }
}

function toggleTask(id: number) {
  const cur = filters.value.taskIds ?? []
  const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]
  setFilter('taskIds', next.length > 0 ? next : null)
}

function toggleResource(id: number) {
  const cur = filters.value.resourceIds ?? []
  const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]
  setFilter('resourceIds', next.length > 0 ? next : null)
}

function reset() {
  filters.value = {}
  searchKeyword.value = ''
}

// SegmentControl 桥接：filters.usageType (含 null) ⇄ 非 null 的 'ALL' | UsageType
type SegmentUsageType = Exclude<ResourceUsageFilterUsageType, null>
function setUsageType(t: UsageType | 'ALL') {
  setFilter('usageType', t === 'ALL' ? null : t)
}
const usageTypeSegmentValue = computed<SegmentUsageType>({
  get: () => (filters.value.usageType ?? 'ALL') as SegmentUsageType,
  set: (v) => setUsageType(v),
})

const usageTypeOptions: ReadonlyArray<SegmentOption<SegmentUsageType>> = [
  { value: 'ALL', label: '全部' },
  { value: 'ACTUAL', label: '实际' },
  { value: 'PLANNED', label: '计划' },
]

const selectedTaskIds = computed(() => filters.value.taskIds ?? [])
const selectedResourceIds = computed(() => filters.value.resourceIds ?? [])
</script>

<template>
  <div class="p-4 panel mb-4">
    <div
      class="px-5 py-4 border-b border-base-content/10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3"
    >
      <!-- 日期 from -->
      <fieldset class="fieldset">
        <label class="fieldset-label text-xs">开始日期</label>
        <input
          type="date"
          :value="filters.dateFrom || ''"
          class="input h-9 text-sm"
          @change="(e) => setFilter('dateFrom', (e.target as HTMLInputElement).value || null)"
        />
      </fieldset>
      <!-- 日期 to -->
      <fieldset class="fieldset">
        <label class="fieldset-label text-xs">结束日期</label>
        <input
          type="date"
          :value="filters.dateTo || ''"
          class="input h-9 text-sm"
          @change="(e) => setFilter('dateTo', (e.target as HTMLInputElement).value || null)"
        />
      </fieldset>
      <!-- 批次 ID -->
      <fieldset class="fieldset">
        <label class="fieldset-label text-xs">批次 ID</label>
        <input
          type="text"
          :value="filters.batchId || ''"
          class="input h-9 text-sm"
          placeholder="输入批次 UUID（可选）"
          @change="(e) => setFilter('batchId', (e.target as HTMLInputElement).value || null)"
        />
      </fieldset>
      <!-- 重置 -->
      <fieldset class="fieldset">
        <label class="fieldset-label text-xs">&nbsp;</label>
        <button class="btn btn-sm btn-ghost" @click="reset">
          <span class="material-symbols-outlined icon-sm">refresh</span>
          重置筛选
        </button>
      </fieldset>
    </div>

    <!-- 用量类型筛选 -->
    <div class="px-5 py-3 border-b border-base-content/10 flex flex-wrap items-center gap-3">
      <span class="text-sm text-base-content/70">用量类型</span>
      <SegmentControl
        v-model="usageTypeSegmentValue"
        :options="usageTypeOptions"
        aria-label="用量类型"
      />
    </div>

    <div class="px-5 py-3 grid grid-cols-1 md:grid-cols-2 gap-4">
      <!-- 任务多选 -->
      <div>
        <div class="text-xs text-fg-muted mb-1">任务筛选</div>
        <div class="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
          <span
            v-for="t in tasks"
            :key="t.id"
            class="badge badge-sm cursor-pointer transition-colors"
            :class="selectedTaskIds.includes(t.id) ? 'badge-primary' : 'badge-outline'"
            @click="toggleTask(t.id)"
          >
            {{ t.code ? `${t.code}` : t.name }}
          </span>
          <span v-if="tasks.length === 0" class="text-xs text-base-content/40">暂无任务</span>
        </div>
      </div>
      <!-- 资源多选 -->
      <div>
        <div class="text-xs text-fg-muted mb-1">资源筛选</div>
        <fieldset class="fieldset mb-1">
          <label class="input w-full flex items-center gap-2">
            <span class="material-symbols-outlined icon-sm">search</span>
            <input
              v-model="searchKeyword"
              type="search"
              class="grow bg-transparent focus:outline-none"
              placeholder="搜索资源"
            />
          </label>
        </fieldset>
        <div class="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
          <span
            v-for="r in allResources"
            :key="r.id"
            class="badge badge-sm cursor-pointer transition-colors"
            :class="selectedResourceIds.includes(r.id) ? 'badge-primary' : 'badge-outline'"
            @click="toggleResource(r.id)"
          >
            {{ r.name }}
          </span>
          <span v-if="allResources.length === 0" class="text-xs text-base-content/40"
            >暂无资源</span
          >
        </div>
      </div>
    </div>
  </div>
</template>
