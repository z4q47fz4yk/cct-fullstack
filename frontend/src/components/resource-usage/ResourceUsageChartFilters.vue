<script setup lang="ts">
/**
 * ResourceUsageChartFilters - 统计 tab 资源选择器
 *
 * 按 category 过滤 + 资源多选
 * 直接使用 useResourceApi
 */
import { ref, computed, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useQuery } from '@pinia/colada'
import ResourceCategoryTabs from '@/components/resource/ResourceCategoryTabs.vue'
import type { ResourceCategory } from '@/types/resource'
import type { ResourceResp } from '@/client/types.gen'

const selectedResourceIds = defineModel<number[]>('selectedResourceIds', { required: true })

const activeCategory = ref<ResourceCategory>('labor')
const searchKeyword = ref('')
const debouncedSearch = ref('')
const updateDebouncedSearch = useDebounceFn((v: string) => {
  debouncedSearch.value = v
}, 300)
watch(searchKeyword, (v) => updateDebouncedSearch(v))

// 拉取当前 category 的资源（per_page: FETCH_ALL_PAGE_SIZE）
const { currentProjectId } = useProjectContext()
const { state: resourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: {
      category: activeCategory.value,
      name: debouncedSearch.value || undefined,
      per_page: FETCH_ALL_PAGE_SIZE,
    },
  }),
)
const currentCategoryResources = computed<ResourceResp[]>(
  () => resourcesState.value?.data?.items ?? [],
)

function toggleResource(id: number) {
  const cur = selectedResourceIds.value
  if (cur.includes(id)) {
    selectedResourceIds.value = cur.filter((x) => x !== id)
  } else {
    selectedResourceIds.value = [...cur, id]
  }
}

function clearAll() {
  selectedResourceIds.value = []
}
</script>

<template>
  <div class="p-4 panel mb-4">
    <div class="px-5 py-4 border-b border-base-content/10">
      <h3 class="section-title">资源分类</h3>
      <ResourceCategoryTabs v-model:selected-category="activeCategory" />
    </div>

    <div class="px-5 py-4">
      <div class="flex items-center justify-between mb-2">
        <div class="text-sm text-base-content/70">已选 {{ selectedResourceIds.length }} 个资源</div>
        <button
          v-if="selectedResourceIds.length > 0"
          class="btn btn-xs btn-ghost"
          @click="clearAll"
        >
          <span class="material-symbols-outlined icon-sm">clear_all</span>
          清空
        </button>
      </div>

      <fieldset class="fieldset mb-2">
        <label class="input w-full flex items-center gap-2">
          <span class="material-symbols-outlined icon-sm">search</span>
          <input
            v-model="searchKeyword"
            type="search"
            class="grow bg-transparent focus:outline-none"
            placeholder="搜索当前分类下的资源..."
          />
        </label>
      </fieldset>

      <div class="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
        <span
          v-for="r in currentCategoryResources"
          :key="r.id"
          class="badge badge-sm cursor-pointer transition-colors"
          :class="selectedResourceIds.includes(r.id) ? 'badge-primary' : 'badge-outline'"
          @click="toggleResource(r.id)"
        >
          {{ r.name }}
        </span>
        <span v-if="currentCategoryResources.length === 0" class="text-xs text-base-content/40">
          该分类下暂无资源
        </span>
      </div>
    </div>
  </div>
</template>
