<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import type { ResourceCategory, ResourcePublicCopyReq } from '@/client/types.gen'
import { categoryConfigMap } from '@/types/resource'
import { usePublicResources } from '@/composables/usePublicResourceApi'
import { confirmInfo } from '@/composables/useConfirm'
import ResourceCategoryTabs from '@/components/resource/ResourceCategoryTabs.vue'
import ResourceSearch from '@/components/resource/ResourceSearch.vue'
import PaginationBar from '@/components/common/PaginationBar.vue'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { fmtNumber } from '@/utils/format'

const show = defineModel<boolean>('show', { required: true })

const emit = defineEmits<{
  (e: 'submit', payload: ResourcePublicCopyReq): void
}>()

// 内部筛选 / 分页状态
const activeCategory = ref<ResourceCategory>('labor')
const searchQuery = ref('')
// 名称关键字：服务端 LIKE 包含匹配（与资源管理页搜索框一致，防抖 300ms 后生效）
const debouncedSearch = ref('')
const updateDebouncedSearch = useDebounceFn((v: string) => {
  debouncedSearch.value = v
}, 300)
watch(searchQuery, (v) => updateDebouncedSearch(v))
const currentPage = ref(1)
const pageSize = ref(10)

// 跨分页累计的已选资源 ID
const selectedIds = ref<Set<number>>(new Set())

const { publicResources, totalCount, isLoading, error, refresh } = usePublicResources({
  category: activeCategory,
  searchQuery: debouncedSearch,
  page: currentPage,
  pageSize,
})

// 切换分类 / 搜索时回到第 1 页
watch([activeCategory, debouncedSearch], () => {
  currentPage.value = 1
})

// 模态框关闭时清空所有选择状态
watch(show, (v) => {
  if (!v) {
    selectedIds.value = new Set()
    searchQuery.value = ''
    debouncedSearch.value = ''
    currentPage.value = 1
    activeCategory.value = 'labor'
  }
})

const selectedCount = computed(() => selectedIds.value.size)

const allOnPageSelected = computed(
  () =>
    publicResources.value.length > 0 &&
    publicResources.value.every((r) => selectedIds.value.has(r.id)),
)

function toggleRow(id: number, checked: boolean) {
  if (checked) selectedIds.value.add(id)
  else selectedIds.value.delete(id)
  selectedIds.value = new Set(selectedIds.value)
}

function toggleSelectAll() {
  if (allOnPageSelected.value) {
    publicResources.value.forEach((r) => selectedIds.value.delete(r.id))
  } else {
    publicResources.value.forEach((r) => selectedIds.value.add(r.id))
  }
  selectedIds.value = new Set(selectedIds.value)
}

function submitSelected() {
  if (selectedIds.value.size === 0) return
  emit('submit', { ids: Array.from(selectedIds.value) })
}

async function confirmImportAllByCategory() {
  const cat = activeCategory.value
  const label = categoryConfigMap[cat].label
  const { confirmed } = await confirmInfo(
    `将导入「${label}」分类下的全部公共资源（约 ${totalCount.value} 项）。\n若目标项目已存在同名资源，将自动跳过。`,
    '按分类全部导入',
  )
  if (!confirmed) return
  emit('submit', { category: cat })
}

function closeModal() {
  show.value = false
}
</script>

<template>
  <BaseModal
    v-model:open="show"
    class="max-w-5xl p-0 flex flex-col max-h-[90vh]"
    @close="closeModal"
  >
    <!-- 头部 -->
    <div class="flex items-center justify-between px-5 py-4 border-b border-base-300/30">
      <div>
        <h3 class="font-bold text-lg text-base-content">从公共资源导入</h3>
        <p class="text-xs text-fg-muted mt-1">
          公共资源为系统预置字典，导入后即成为本项目资源，可自由编辑。
        </p>
      </div>
      <button
        class="btn btn-ghost btn-ghost-outline btn-sm btn-square"
        type="button"
        @click="closeModal"
      >
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>

    <!-- 筛选区 -->
    <div
      class="px-5 py-3 border-b border-base-300/20 flex items-center justify-between gap-4 flex-wrap"
    >
      <ResourceCategoryTabs v-model:selected-category="activeCategory" :disabled="isLoading" />
      <ResourceSearch
        v-model:query="searchQuery"
        placeholder="搜索公共资源名称..."
        :disabled="isLoading"
        class="w-64!"
      />
    </div>

    <!-- 错误状态 -->
    <ErrorState
      v-if="error"
      class="m-5"
      title="加载公共资源失败"
      description="无法获取公共资源列表，请检查网络连接"
      @retry="refresh"
    />

    <!-- 表格 -->
    <div v-else class="flex-1 overflow-y-auto px-5 py-3">
      <div class="overflow-x-auto card">
        <table class="table">
          <thead>
            <tr>
              <th class="w-12">
                <label class="label cursor-pointer justify-center">
                  <input
                    type="checkbox"
                    class="checkbox checkbox-sm"
                    :checked="allOnPageSelected"
                    :disabled="publicResources.length === 0"
                    @change="toggleSelectAll"
                  />
                </label>
              </th>
              <th class="w-16 text-center">类别</th>
              <th class="flex-1">资源名称</th>
              <th class="w-24">单位</th>
              <th colspan="2" class="text-center">单价</th>
              <th colspan="2" class="text-center">碳排放因子</th>
            </tr>
          </thead>
          <tbody>
            <template v-if="publicResources.length > 0">
              <tr v-for="r in publicResources" :key="r.id" class="transition-colors">
                <td class="text-center">
                  <label class="label cursor-pointer justify-center">
                    <input
                      type="checkbox"
                      class="checkbox checkbox-sm"
                      :checked="selectedIds.has(r.id)"
                      @change="(e) => toggleRow(r.id, (e.target as HTMLInputElement).checked)"
                    />
                  </label>
                </td>
                <td class="text-center">
                  <span
                    class="material-symbols-outlined icon-md"
                    :title="categoryConfigMap[r.category].label"
                  >
                    {{ categoryConfigMap[r.category].icon }}
                  </span>
                </td>
                <td>
                  <div class="font-medium text-base-content">{{ r.name }}</div>
                  <div v-if="r.description" class="text-xs text-fg-muted mt-0.5 line-clamp-1">
                    {{ r.description }}
                  </div>
                </td>
                <td class="text-neutral-content">{{ r.unit }}</td>
                <td class="table-num w-24 pr-1">
                  <span class="font-num font-medium">{{ fmtNumber(r.unitPrice, 2) }}</span>
                </td>
                <td class="w-20 pl-0">
                  <span class="text-neutral-content text-sm">元/{{ r.unit }}</span>
                </td>
                <td class="table-num w-24 pr-1">
                  <span class="font-num">{{ fmtNumber(r.carbonFactor, 2) }}</span>
                </td>
                <td class="w-24 pl-0">
                  <span class="text-neutral-content text-sm text-nowrap">kg/{{ r.unit }}</span>
                </td>
              </tr>
            </template>

            <TableEmptyState
              v-else-if="!isLoading"
              :colspan="8"
              title="暂无公共资源"
              description="该分类下没有匹配的公共资源"
              icon="cloud_off"
            />

            <tr v-if="isLoading">
              <td :colspan="8" class="text-center py-10">
                <span class="loading loading-spinner loading-md text-primary"></span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="!error" class="px-5 pb-3 mt-4">
      <PaginationBar
        v-model:current="currentPage"
        v-model:page-size="pageSize"
        :total="totalCount"
      />
    </div>

    <!-- 底部操作栏 -->
    <div
      class="border-t border-base-300/30 px-5 py-3 flex items-center justify-between bg-base-300/10"
    >
      <button
        class="btn btn-sm btn-ghost btn-ghost-outline"
        type="button"
        :disabled="isLoading"
        @click="confirmImportAllByCategory"
      >
        <span class="material-symbols-outlined icon-sm">select_all</span>
        按当前分类全部导入
      </button>
      <div class="flex items-center gap-2">
        <button class="btn btn-ghost btn-ghost-outline btn-sm" type="button" @click="closeModal">
          取消
        </button>
        <button
          class="btn btn-primary btn-sm"
          type="button"
          :disabled="selectedCount === 0"
          @click="submitSelected"
        >
          <span class="material-symbols-outlined icon-sm">download</span>
          导入所选（{{ selectedCount }}）
        </button>
      </div>
    </div>
  </BaseModal>
</template>
