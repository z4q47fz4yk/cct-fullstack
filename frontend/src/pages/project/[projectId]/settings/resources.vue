<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import type { ResourceCategory } from '@/types/resource'
import type {
  ResourceResp,
  ResourceCreate,
  ResourcePublicCopyReq,
  ResourcePublicCopyResp,
  ResourceWithConfigResp,
} from '@/client/types.gen'
import { useResourceApi } from '@/composables/useResourceApi'
import { useConstraintApi } from '@/composables/useConstraintApi'
import { useReuseConfigApi } from '@/composables/useReuseConfigApi'
import { useTagApi } from '@/composables/useTagApi'
import { useCopyPublicResources } from '@/composables/usePublicResourceApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { confirmDanger, confirmInfo } from '@/composables/useConfirm'
import { notifyError } from '@/composables/useToast'
import { formatHttpError } from '@/utils/error'
import PaginationBar from '@/components/common/PaginationBar.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ResourceCategoryTabs from '@/components/resource/ResourceCategoryTabs.vue'
import ResourceTable from '@/components/resource/ResourceTable.vue'
import ResourceForm from '@/components/resource/ResourceForm.vue'
import PublicResourceImportModal from '@/components/resource/PublicResourceImportModal.vue'
import TagFilterDropdown from '@/components/tag/TagFilterDropdown.vue'
import type { ConstraintDraft, ReuseDraft } from '@/types/resource'

definePage({
  meta: {
    title: '资源管理',
    icon: 'inventory_2',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 3,
  },
})

/* ── 过滤与分页（全部由后端 listResources 承担） ──────────── */

// 分类：null = 全部
const activeCategory = ref<ResourceCategory | null>(null)
// 名称关键字：服务端 LIKE，包含匹配
const nameSearch = ref<string>('')
const debouncedName = ref<string>('')
const updateDebouncedName = useDebounceFn((v: string) => {
  debouncedName.value = v
}, 300)
watch(nameSearch, (v) => updateDebouncedName(v))

const hasConstraintOnly = ref(false)
/** 可复用（仅材料）：勾选时锁定 category=material 并禁用分类 tab */
const reuseOnly = ref(false)
// 勾选「可复用」前记住分类，取消勾选时还原（undefined=未勾选过）
const categoryBeforeReuse = ref<ResourceCategory | null | undefined>(undefined)

watch(reuseOnly, (on) => {
  if (on) {
    // 「可复用」与「有限制」互斥：勾选「可复用」时清空「有限制」
    hasConstraintOnly.value = false
    categoryBeforeReuse.value = activeCategory.value
    activeCategory.value = 'material'
  } else {
    if (categoryBeforeReuse.value !== undefined) {
      activeCategory.value = categoryBeforeReuse.value
    }
    categoryBeforeReuse.value = undefined
  }
})

watch(hasConstraintOnly, (on) => {
  if (on) {
    // 「有限制」与「可复用」互斥：勾选「有限制」时清空「可复用」
    reuseOnly.value = false
  }
})

// tag 多选（AND）：直接传给后端 tag_ids
const selectedTagIds = ref<number[]>([])

// 服务端分页
const currentPage = ref(1)
const pageSize = ref(10)

// 任意过滤变化都重置到第 1 页
watch(
  [activeCategory, debouncedName, hasConstraintOnly, reuseOnly, selectedTagIds, pageSize],
  () => {
    currentPage.value = 1
  },
)

/* ── 数据源：服务端分页/过滤驱动，每条资源已附 tags / constraint / reuse_config ── */
const {
  pagedResources,
  totalCount,
  isLoading,
  error,
  refresh,
  createResource,
  updateResource,
  deleteResource,
} = useResourceApi({
  category: activeCategory,
  name: debouncedName,
  constrained: hasConstraintOnly,
  reusable: reuseOnly,
  tagIds: selectedTagIds,
  page: currentPage,
  pageSize,
})

// 限制 / 周转复用 mutation（CRUD 写入；列表已随 resources 一次性返回）
const { createConstraint, updateConstraint, deleteConstraint } = useConstraintApi()
const { createConfig, updateConfig, deleteConfig } = useReuseConfigApi()

const { tags: catalogTags } = useTagApi()

/* ── 新增/编辑资源（弹窗内一并管理 限制/周转复用） ───────────── */

const showModal = ref(false)
const isEditing = ref(false)
const editingResourceId = ref<number | null>(null)
const saving = ref(false)

const emptyResource = (): ResourceCreate => ({
  name: '',
  description: '',
  category: 'labor' as ResourceCategory,
  unit: '',
  unitPrice: 0,
  carbonFactor: 0,
})

const formData = ref<ResourceCreate>(emptyResource())

const constraintDraft = ref<ConstraintDraft>({
  enabled: false,
  maxUsage: null,
  description: '',
})
const reuseDraft = ref<ReuseDraft>({
  enabled: false,
  maxReuses: 1,
  reuseCount: 1,
  affectCost: false,
  description: null,
})

const formError = ref('')

function openAddModal() {
  isEditing.value = false
  editingResourceId.value = null
  // 新增资源：分类显式选择，不默认当前筛选分类
  formData.value = emptyResource()
  constraintDraft.value = { enabled: false, maxUsage: null, description: '' }
  reuseDraft.value = {
    enabled: false,
    maxReuses: 1,
    reuseCount: 1,
    affectCost: false,
    description: null,
  }
  formError.value = ''
  showModal.value = true
}

function openEditModal(resource: ResourceWithConfigResp) {
  isEditing.value = true
  editingResourceId.value = resource.id
  formData.value = {
    name: resource.name,
    description: resource.description,
    category: resource.category,
    unit: resource.unit,
    unitPrice: resource.unitPrice,
    carbonFactor: resource.carbonFactor,
  }

  // 直接从资源条目读附带字段（listResources 已 include_constraint / include_reuse_config）
  const constraint = resource.constraint
  constraintDraft.value = constraint
    ? { enabled: true, maxUsage: constraint.maxUsage, description: constraint.description ?? '' }
    : { enabled: false, maxUsage: null, description: '' }

  const reuse = resource.reuseConfig
  reuseDraft.value = reuse
    ? {
        enabled: true,
        maxReuses: reuse.maxReuses,
        reuseCount: reuse.reuseCount,
        affectCost: reuse.affectCost,
        description: reuse.description ?? null,
      }
    : { enabled: false, maxReuses: 1, reuseCount: 1, affectCost: false, description: null }

  formError.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  formError.value = ''
}

async function saveResource() {
  formError.value = ''
  if (!formData.value.name || !formData.value.unit) {
    formError.value = '请填写资源名称和计量单位'
    return
  }
  saving.value = true
  try {
    if (isEditing.value && editingResourceId.value != null) {
      const id = editingResourceId.value
      await updateResource({
        path: { project_id: currentProjectId.value!, id },
        body: formData.value,
      })
      await syncConstraintFor(id)
      await syncReuseFor(id)
    } else {
      const created = await createResource({
        path: { project_id: currentProjectId.value! },
        body: formData.value,
      })
      if (created) {
        await syncConstraintFor(created.id)
        await syncReuseFor(created.id)
      }
    }
    // 限制 / 周转复用的增删改不会自动让 resources 缓存失效：
    // 这些字段通过 include_* 随 listResources 一次性返回，保存后必须刷新。
    await refresh()
    closeModal()
  } catch (e) {
    formError.value = formatHttpError(e, '保存失败，请重试')
    console.error('Save resource failed:', e)
  } finally {
    saving.value = false
  }
}

/** 限制增删改编排：无→有 create；有→无 delete；有→改 update */
async function syncConstraintFor(resourceId: number) {
  // 在当前页资源条目里找 constraint 字段（listResources 已 include_constraint=true）。
  // 编辑资源时弹窗打开前已同步到该资源所在页；若恰好不在当前页，
  // 由弹窗回填兜底（草稿可能为空，但保存时仍按"无→有 create"处理）。
  const existing = pagedResources.value.find((r) => r.id === resourceId)?.constraint
  const maxUsage = constraintDraft.value.maxUsage ?? 0
  const description = constraintDraft.value.description?.trim() ?? ''
  if (!constraintDraft.value.enabled || maxUsage <= 0) {
    if (existing) {
      await deleteConstraint({
        path: { project_id: currentProjectId.value!, id: existing.id },
      })
    }
    return
  }
  if (existing) {
    await updateConstraint({
      path: { project_id: currentProjectId.value!, id: existing.id },
      body: { maxUsage, description },
    })
  } else {
    await createConstraint({
      path: { project_id: currentProjectId.value! },
      body: { resourceId, maxUsage, description },
    })
  }
}

/** 周转复用编排：仅 material 生效；否则删除既有配置 */
async function syncReuseFor(resourceId: number) {
  const existing = pagedResources.value.find((r) => r.id === resourceId)?.reuseConfig
  const isMaterial = formData.value.category === 'material'
  if (!isMaterial || !reuseDraft.value.enabled) {
    if (existing) {
      await deleteConfig({
        path: { project_id: currentProjectId.value!, id: existing.id },
      })
    }
    return
  }
  const body = {
    maxReuses: reuseDraft.value.maxReuses,
    reuseCount: reuseDraft.value.reuseCount,
    affectCost: reuseDraft.value.affectCost,
    description: reuseDraft.value.description?.trim() || null,
  }
  if (existing) {
    await updateConfig({
      path: { project_id: currentProjectId.value!, id: existing.id },
      body,
    })
  } else {
    await createConfig({
      path: { project_id: currentProjectId.value! },
      body: { resourceId, ...body },
    })
  }
}

async function handleDeleteResource(resource: ResourceResp) {
  const { confirmed } = await confirmDanger(
    `确定要删除资源 "${resource.name}" 吗？关联的限制与周转配置将一并删除，此操作不可恢复。`,
  )
  if (!confirmed) return
  try {
    await deleteResource({ path: { project_id: currentProjectId.value!, id: resource.id } })
    // 级联删除的约束/周转配置随 listResources 单接口刷新
    await refresh()
  } catch (e) {
    notifyError({ title: '删除失败', description: formatHttpError(e, '请稍后重试') })
    console.error('Delete resource failed:', e)
  }
}

/* 公共资源导入（保留原功能） */
const showImportModal = ref(false)
const { copyPublicResources, isCopying } = useCopyPublicResources()
const { currentProjectId } = useProjectContext()

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
    notifyError({ title: '导入失败', description: formatHttpError(e, '请稍后重试') })
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
      <section class="panel p-0" aria-labelledby="list-title">
        <!-- 筛选器：名称 / 分类(全部=null) / 限制 / 可复用 / 标签(AND) -->
        <div class="m-4 flex flex-wrap items-center gap-x-4 gap-y-2">
          <fieldset class="fieldset w-56 shrink-0">
            <label class="input w-full flex items-center gap-2">
              <span class="material-symbols-outlined icon-sm">search</span>
              <input
                v-model="nameSearch"
                type="search"
                class="grow bg-transparent focus:outline-none"
                placeholder="搜索资源名称..."
                :disabled="isLoading"
              />
            </label>
          </fieldset>

          <ResourceCategoryTabs
            v-model:selected-category="activeCategory"
            :disabled="isLoading || reuseOnly"
            all-option
            clearable
            class="shrink-0"
          />

          <div class="flex items-center gap-4 text-sm">
            <label class="flex items-center gap-1.5 cursor-pointer select-none">
              <input
                v-model="hasConstraintOnly"
                type="checkbox"
                class="checkbox checkbox-sm"
                :disabled="isLoading || reuseOnly"
              />
              <span class="text-fg-muted">有限制</span>
            </label>
            <label class="flex items-center gap-1.5 cursor-pointer select-none">
              <input
                v-model="reuseOnly"
                type="checkbox"
                class="checkbox checkbox-sm"
                :disabled="isLoading || hasConstraintOnly"
              />
              <span class="text-fg-muted">可复用</span>
            </label>
            <TagFilterDropdown v-model:selected="selectedTagIds" :tags="catalogTags" />
          </div>

          <span class="ml-auto text-xs text-fg-subtle shrink-0">
            共 <span class="font-num font-medium text-base-content">{{ totalCount }}</span> 项资源
          </span>
        </div>

        <!-- 项目资源列表 -->
        <ResourceTable
          :resources="pagedResources"
          :category="activeCategory ?? 'labor'"
          @edit="openEditModal"
          @delete="handleDeleteResource"
          class="border-t border-b border-base-content/30"
        />

        <div class="px-4 py-3">
          <PaginationBar
            v-model:current="currentPage"
            v-model:page-size="pageSize"
            :total="totalCount"
          />
        </div>
      </section>
    </div>
  </template>

  <!-- 新增/编辑资源模态框（内嵌 限制/周转复用） -->
  <ResourceForm
    v-model:show="showModal"
    v-model:resource="formData"
    v-model:constraint="constraintDraft"
    v-model:reuse="reuseDraft"
    :title="isEditing ? '编辑资源' : '添加资源'"
    :is-submitting="saving"
    :error="formError"
    configurable
    :require-category="!isEditing"
    @submit="saveResource"
    @cancel="closeModal"
  />

  <!-- 从公共资源导入模态框 -->
  <PublicResourceImportModal v-model:show="showImportModal" @submit="handleImportSubmit" />
</template>
