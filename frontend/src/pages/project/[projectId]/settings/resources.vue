<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useQuery } from '@pinia/colada'
import type { ResourceCategory } from '@/types/resource'
import { categoryConfigMap } from '@/types/resource'
import { getCategoryColor } from '@/utils/themeColors'
import type {
  ResourceResp,
  ResourceCreate,
  ResourcePublicCopyReq,
  ResourcePublicCopyResp,
} from '@/client/types.gen'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import { useResourceApi } from '@/composables/useResourceApi'
import { useCopyPublicResources } from '@/composables/usePublicResourceApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { confirmDanger, confirmInfo } from '@/composables/useConfirm'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import PaginationBar from '@/components/common/PaginationBar.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import SearchableSelect from '@/components/common/SearchableSelect.vue'
import ResourceCategoryTabs from '@/components/resource/ResourceCategoryTabs.vue'
import ResourceTable from '@/components/resource/ResourceTable.vue'
import ResourceForm from '@/components/resource/ResourceForm.vue'
import PublicResourceImportModal from '@/components/resource/PublicResourceImportModal.vue'
import type { SelectOption } from '@/types/select'

definePage({
  meta: {
    title: '资源管理',
    icon: 'inventory_2',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 3,
  },
})

const activeCategory = ref<ResourceCategory>('labor')
const categories: ResourceCategory[] = ['labor', 'machinery', 'material', 'transport', 'others']
const searchQuery = ref('')

const currentPage = ref(1)
const pageSize = ref(10)

const {
  apiResources,
  totalCount,
  isLoading,
  error,
  refresh,
  categoryStats,
  isStatsLoading,
  createResource,
  updateResource,
  deleteResource,
  isSubmitting,
} = useResourceApi({
  category: activeCategory,
  searchQuery: searchQuery,
  page: currentPage,
  pageSize: pageSize,
})

const { currentProjectId } = useProjectContext()

const { copyPublicResources, isCopying } = useCopyPublicResources()

// SearchableSelect 搜索关键字（与表格筛选分离）
const searchKeyword = ref('')

const { state: resourceSelectState } = useQuery(() => ({
  ...listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: {
      name: searchKeyword.value || undefined,
      per_page: FETCH_ALL_PAGE_SIZE,
    },
  }),
  enabled: currentProjectId.value !== null,
}))

const resourceSelectOptions = computed<SelectOption<ResourceResp, number | null>[]>(() => {
  const items = resourceSelectState.value?.data?.items ?? []
  return items.map((r) => ({
    raw: r,
    value: r.id,
    label: r.name,
    description: `${r.unit}`,
  }))
})

// SearchableSelect 选中的资源 ID
const selectedResourceId = ref<number | null>(null)

// 搜索前保存的分类，搜索关闭后恢复
const savedCategory = ref<ResourceCategory | null>(null)

// 用户开始搜索时，保存当前分类
watch(searchKeyword, (keyword) => {
  if (keyword && savedCategory.value === null) {
    savedCategory.value = activeCategory.value
  }
})

// 选中资源时，切换到该资源所属分类并设置搜索关键字过滤表格
watch(selectedResourceId, (id) => {
  if (id == null) {
    searchQuery.value = ''
  } else {
    const items = resourceSelectState.value?.data?.items ?? []
    const found = items.find((r) => r.id === id)
    if (found) {
      activeCategory.value = found.category
      searchQuery.value = found.name
    }
  }
})

// 搜索关闭时恢复分类
function onSearchClose() {
  if (savedCategory.value !== null) {
    activeCategory.value = savedCategory.value
    savedCategory.value = null
  }
}

const showModal = ref(false)
const isEditing = ref(false)
const editingResourceId = ref<number | null>(null)

// 公共资源导入模态框
const showImportModal = ref(false)

const formData = ref<ResourceCreate>({
  name: '',
  category: 'labor',
  unitPrice: 0,
  unit: '',
  carbonFactor: 0,
  description: '',
})

const formError = ref('')

const totalResources = totalCount

// 切换分类或搜索时重置页码
watch([activeCategory, searchQuery], () => {
  currentPage.value = 1
})

// 切换分类时重置选中的资源
watch(activeCategory, () => {
  selectedResourceId.value = null
  searchKeyword.value = ''
  savedCategory.value = null
})

const statsMap = computed(() => {
  const map = new Map<ResourceCategory, number>()
  categoryStats.value.forEach((stat) => {
    map.set(stat.category, stat.count)
  })
  return map
})

function getCount(category: ResourceCategory): number {
  return statsMap.value.get(category) ?? 0
}

function openAddModal() {
  isEditing.value = false
  editingResourceId.value = null
  resetForm()
  formError.value = ''
  showModal.value = true
}

function openEditModal(resource: ResourceResp) {
  isEditing.value = true
  editingResourceId.value = resource.id
  formData.value = {
    name: resource.name,
    category: resource.category,
    unitPrice: resource.unitPrice,
    unit: resource.unit,
    carbonFactor: resource.carbonFactor,
    description: resource.description,
  }
  formError.value = ''
  showModal.value = true
}

function resetForm() {
  formData.value = {
    name: '',
    category: activeCategory.value,
    unitPrice: 0,
    unit: '',
    carbonFactor: 0,
    description: '',
  }
}

function closeModal() {
  showModal.value = false
  resetForm()
  formError.value = ''
}

async function saveResource() {
  formError.value = ''

  if (!formData.value.name || !formData.value.unit) {
    formError.value = '请填写资源名称和计量单位'
    return
  }

  try {
    if (isEditing.value && editingResourceId.value) {
      await updateResource({
        path: { project_id: currentProjectId.value!, id: editingResourceId.value },
        body: formData.value,
      })
    } else {
      await createResource({ path: { project_id: currentProjectId.value! }, body: formData.value })
    }
    closeModal()
  } catch (e) {
    formError.value = '保存失败，请重试'
    console.error('Save resource failed:', e)
  }
}

const deletingId = ref<number | null>(null)

async function handleDeleteResource(resource: ResourceResp) {
  const { confirmed } = await confirmDanger(
    `确定要删除资源 "${resource.name}" 吗？此操作不可恢复。`,
  )

  if (!confirmed) return

  deletingId.value = resource.id
  try {
    await deleteResource({ path: { project_id: currentProjectId.value!, id: resource.id } })
  } catch (e) {
    console.error('Delete resource failed:', e)
  } finally {
    deletingId.value = null
  }
}

/**
 * 公共资源导入提交处理
 * ResourcePublicCopyReq 的 { ids } 与 { category } 严格互斥，按后端 OpenAPI 描述必须二选一
 */
async function handleImportSubmit(payload: ResourcePublicCopyReq) {
  if (!currentProjectId.value) return
  let body: ResourcePublicCopyReq
  if (payload.ids && payload.ids.length > 0) {
    body = { ids: payload.ids }
  } else if (payload.category) {
    body = { category: payload.category }
  } else {
    return
  }
  try {
    const result: ResourcePublicCopyResp = await copyPublicResources(body)
    showImportModal.value = false
    await showImportSummary(result)
  } catch (e) {
    console.error('Import public resources failed:', e)
  }
}

async function showImportSummary(r: ResourcePublicCopyResp) {
  const copied = r.copied?.length ?? 0
  const skipped = r.skipped?.length ?? 0
  const notFound = r.notFound?.length ?? 0
  let msg = `共处理 ${r.totalRequested} 项：成功 ${copied} 项`
  if (skipped > 0) msg += `，跳过 ${skipped} 项（目标项目已存在同名）`
  if (notFound > 0) msg += `，未找到 ${notFound} 项`
  await confirmInfo(msg, '导入完成')
}

function retryLoad() {
  refresh()
}
</script>

<template>
  <!-- 操作按钮 -->
  <Teleport defer to="#header-actions">
    <button
      class="btn btn-secondary gap-1 px-4"
      :disabled="isLoading || isCopying"
      @click="showImportModal = true"
    >
      <span class="material-symbols-outlined icon-sm">library_add</span>
      从公共资源导入
    </button>
    <button class="btn btn-primary gap-1 px-5" :disabled="isLoading" @click="openAddModal">
      <span class="material-symbols-outlined icon-sm">add</span>
      添加资源
    </button>
  </Teleport>

  <ErrorState
    v-if="error"
    title="加载失败"
    description="无法获取资源列表，请检查网络连接"
    @retry="retryLoad"
  />

  <!-- 正常内容 -->
  <template v-else>
    <div class="space-y-4">
      <!-- 资源数量一览 -->
      <section class="hidden" aria-labelledby="stats-title">
        <!-- <h2 id="stats-title" class="section-title">资源数量一览</h2> -->
        <div class="flex flex-wrap gap-3">
          <div
            v-for="category in categories"
            :key="category"
            class="flex items-center gap-2 rounded-field px-3 py-2"
            :style="{
              backgroundColor: `color-mix(in oklch, ${getCategoryColor(category)} 10%, transparent)`,
            }"
          >
            <span
              class="material-symbols-outlined icon-sm"
              :style="{ color: getCategoryColor(category) }"
            >
              {{ categoryConfigMap[category].icon }}
            </span>
            <span class="text-sm text-fg-muted">{{ categoryConfigMap[category].label }}</span>
            <span v-if="isStatsLoading" class="loading loading-spinner loading-xs"></span>
            <span v-else class="text-sm font-semibold text-base-content">
              {{ getCount(category) }}
            </span>
            <span class="text-xs text-fg-muted">种</span>
          </div>
        </div>
      </section>

      <section class="panel p-0" aria-labelledby="list-title">
        <!-- 筛选器 -->
        <div class="m-4 flex flex-wrap justify-between items-center gap-4">
          <div class="w-56">
            <SearchableSelect
              v-model:selected-value="selectedResourceId"
              v-model:search="searchKeyword"
              :options="resourceSelectOptions"
              placeholder="搜索资源名称..."
              :disabled="isLoading"
              @close="onSearchClose"
            />
          </div>
          <ResourceCategoryTabs v-model:selected-category="activeCategory" :disabled="isLoading" />
        </div>
        <!-- 项目资源列表 -->
        <div class="">
          <ResourceTable
            :resources="apiResources"
            :category="activeCategory"
            @edit="openEditModal"
            @delete="handleDeleteResource"
            class="border-t border-b border-base-content/30"
          />

          <!-- 分页 -->
          <PaginationBar
            v-model:current="currentPage"
            v-model:page-size="pageSize"
            :total="totalResources"
            class="ml-2 mr-2"
          />
        </div>
      </section>
    </div>
  </template>

  <div v-if="isLoading" class="flex justify-center py-8">
    <span class="loading loading-spinner loading-lg text-primary"></span>
  </div>

  <!-- 添加/编辑资源模态框 -->
  <ResourceForm
    v-model:show="showModal"
    v-model:resource="formData"
    :title="isEditing ? '编辑资源' : '添加资源'"
    :is-submitting="isSubmitting"
    :error="formError"
    @submit="saveResource"
    @cancel="closeModal"
  />

  <!-- 从公共资源导入模态框 -->
  <PublicResourceImportModal v-model:show="showImportModal" @submit="handleImportSubmit" />
</template>
