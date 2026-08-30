<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuery } from '@pinia/colada'
import { useTagApi, useTagTreeByDimension, useTagResources } from '@/composables/useTagApi'
import { useTagDimensionApi } from '@/composables/useTagDimensionApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { formatHttpError } from '@/utils/error'
import BaseModal from '@/components/ui/BaseModal.vue'
import { getTagQuery } from '@/client/@pinia/colada.gen'
import type { TagDimensionResp, TagNodeResp } from '@/client/types.gen'
import type { ResourceCategory } from '@/types/resource'
import { categoryConfigMap } from '@/types/resource'
import { countSubtree, findTagNode, findTagPath } from '@/utils/tagTree'
import TagTree from '@/components/tag/TagTree.vue'
import TagFormModal from '@/components/tag/TagFormModal.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import PaginationBar from '@/components/common/PaginationBar.vue'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import { fmtNumber } from '@/utils/format'

definePage({
  meta: {
    title: '碳排放标签',
    description: '按维度组织标签树，父标签自动汇总子孙标签的碳排放',
    icon: 'label',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 7,
  },
})

const { createTag, updateTag, deleteTag, isSubmitting } = useTagApi()
const {
  dimensions,
  isLoading: dimsLoading,
  error: dimsError,
  refresh: refreshDims,
  createDimension,
  updateDimension,
  deleteDimension,
  isSubmitting: dimsSubmitting,
} = useTagDimensionApi()
const { currentProjectId } = useProjectContext()
const { confirmDanger } = useConfirm()
const { notifySuccess } = useToast()

// ─── 维度选择（左侧列表） ─────────────────────────────────

const selectedDimensionId = ref<number | null>(null)

watch(
  () => dimensions.value,
  (list) => {
    if (selectedDimensionId.value === null && list.length > 0) {
      selectedDimensionId.value = list[0]!.id
    } else if (
      selectedDimensionId.value !== null &&
      !list.some((d) => d.id === selectedDimensionId.value)
    ) {
      selectedDimensionId.value = list[0]?.id ?? null
    }
  },
  { immediate: true },
)

const selectedDimension = computed<TagDimensionResp | null>(
  () => dimensions.value.find((d) => d.id === selectedDimensionId.value) ?? null,
)

// 该维度下的标签树
const { tagTree, isLoading, error, refresh } = useTagTreeByDimension(selectedDimensionId)

// ─── 选中标签 ──────────────────────────────────────────────

const selectedId = ref<number | null>(null)

watch(selectedDimensionId, () => {
  selectedId.value = null
  resPage.value = 1
})

const selectedNode = computed<TagNodeResp | null>(() =>
  selectedId.value === null ? null : (findTagNode(tagTree.value, selectedId.value) ?? null),
)

const selectedPath = computed<string[]>(() =>
  selectedId.value === null ? [] : findTagPath(tagTree.value, selectedId.value).map((n) => n.name),
)

// 选中标签详情（描述 / 创建时间）
const { state: tagDetailState } = useQuery(() => ({
  ...getTagQuery({
    path: { project_id: currentProjectId.value!, id: selectedId.value! },
  }),
  enabled: selectedId.value !== null,
}))

const tagDetail = computed(() => tagDetailState.value?.data)

// ─── 关联资源（分页） ──────────────────────────────────────

const resPage = ref(1)
const resPageSize = ref(10)

const {
  resources,
  totalCount,
  isLoading: resLoading,
} = useTagResources(selectedId, resPage, resPageSize)

watch(selectedId, () => {
  resPage.value = 1
})

const descendantCount = computed(() =>
  selectedNode.value ? countSubtree(selectedNode.value) - 1 : 0,
)

const createdDate = computed(() => tagDetail.value?.createdAt?.slice(0, 10) ?? '—')

// ─── 搜索 ──────────────────────────────────────────────────

const searchQuery = ref('')

// ─── 表单弹窗（标签） ──────────────────────────────────────

const showForm = ref(false)
const editingTag = ref<TagNodeResp | null>(null)
const editingDescription = ref('')
const defaultParentId = ref<number | null>(null)
const formError = ref('')

function openCreate() {
  editingTag.value = null
  defaultParentId.value = null
  formError.value = ''
  showForm.value = true
}

function openCreateChild(parent: TagNodeResp) {
  editingTag.value = null
  defaultParentId.value = parent.id
  formError.value = ''
  showForm.value = true
}

function openEdit(tag: TagNodeResp) {
  editingTag.value = tag
  editingDescription.value = tag.id === selectedId.value ? (tagDetail.value?.description ?? '') : ''
  defaultParentId.value = null
  formError.value = ''
  showForm.value = true
}

async function handleFormSubmit(payload: {
  name: string
  dimensionId: number
  parentId: number | null
  description: string
}) {
  formError.value = ''
  try {
    if (editingTag.value) {
      await updateTag({
        path: { project_id: currentProjectId.value!, id: editingTag.value.id },
        body: {
          name: payload.name,
          dimensionId: payload.dimensionId,
          parentId: payload.parentId,
          description: payload.description,
        },
      })
      notifySuccess('标签已更新')
    } else {
      await createTag({
        path: { project_id: currentProjectId.value! },
        body: {
          name: payload.name,
          dimensionId: payload.dimensionId,
          parentId: payload.parentId,
          description: payload.description,
        },
      })
      notifySuccess('标签已创建')
    }
    showForm.value = false
  } catch (e) {
    formError.value = formatHttpError(e, '保存失败，请重试')
  }
}

function closeForm() {
  showForm.value = false
}

// ─── 删除 ──────────────────────────────────────────────────

async function handleDelete(tag: TagNodeResp) {
  const { confirmed } = await confirmDanger(`确定要删除标签「${tag.name}」吗？`)
  if (!confirmed) return
  try {
    await deleteTag({ path: { project_id: currentProjectId.value!, id: tag.id } })
    if (selectedId.value === tag.id) selectedId.value = null
    notifySuccess('标签已删除')
  } catch (e) {
    console.error('Delete tag failed:', e)
  }
}

// ─── 维度管理 ──────────────────────────────────────────────

const showDimForm = ref(false)
const editingDimension = ref<TagDimensionResp | null>(null)
const dimName = ref('')
const dimDescription = ref('')
const dimError = ref('')

function openCreateDimension() {
  editingDimension.value = null
  dimName.value = ''
  dimDescription.value = ''
  dimError.value = ''
  showDimForm.value = true
}

function openEditDimension(d: TagDimensionResp) {
  editingDimension.value = d
  dimName.value = d.name
  dimDescription.value = d.description
  dimError.value = ''
  showDimForm.value = true
}

async function handleDimensionSubmit() {
  dimError.value = ''
  const name = dimName.value.trim()
  if (!name) {
    dimError.value = '请输入维度名称'
    return
  }
  try {
    if (editingDimension.value) {
      await updateDimension({
        path: { project_id: currentProjectId.value!, id: editingDimension.value.id },
        body: { name, description: dimDescription.value.trim() },
      })
      notifySuccess('维度已更新')
    } else {
      await createDimension({
        path: { project_id: currentProjectId.value! },
        body: { name, description: dimDescription.value.trim() },
      })
      notifySuccess('维度已创建')
    }
    showDimForm.value = false
  } catch (e) {
    dimError.value = formatHttpError(e, '保存失败，请重试')
  }
}

async function handleDeleteDimension(d: TagDimensionResp) {
  const { confirmed } = await confirmDanger(`确定要删除维度「${d.name}」吗？`, '确认删除维度')
  if (!confirmed) return
  try {
    await deleteDimension({ path: { project_id: currentProjectId.value!, id: d.id } })
    notifySuccess('维度已删除')
  } catch (e) {
    console.error('Delete dimension failed:', e)
  }
}

// 该维度下的标签总数（用于维度行计数）
const tagCountByDimension = computed(() => {
  // 维度树按需加载，选中维度时返回其树根节点数
  if (selectedDimensionId.value === null) return 0
  return tagTree.value.length
})

const hasDimensions = computed(() => dimensions.value.length > 0)

function categoryLabel(category: ResourceCategory): string {
  return categoryConfigMap[category]?.label ?? category
}
</script>

<template>
  <Teleport defer to="#header-actions">
    <button
      class="btn btn-primary gap-1 px-5"
      :disabled="isLoading || dimsLoading"
      @click="openCreate"
    >
      <span class="material-symbols-outlined icon-sm">add</span>
      添加标签
    </button>
  </Teleport>

  <ErrorState
    v-if="dimsError"
    title="加载失败"
    description="无法获取标签维度，请检查网络连接"
    @retry="refreshDims"
  />

  <div v-else class="space-y-4">
    <!-- 汇总说明 -->
    <section class="panel px-4 py-3 flex items-center gap-3">
      <span class="material-symbols-outlined text-primary icon-md shrink-0">account_tree</span>
      <p class="text-xs text-fg-muted leading-relaxed">
        标签按维度组织，每个维度一棵树；父标签的碳排放自动汇总其全部子孙标签；跨维度允许重名，选择器会标注维度上下文。
      </p>
    </section>

    <div class="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4 items-start">
      <!-- 左：维度列表 -->
      <section class="panel p-0" aria-labelledby="dimension-list-title">
        <div class="m-4 flex flex-col gap-3">
          <div class="flex items-center justify-between gap-2">
            <h2 id="dimension-list-title" class="section-title m-0">标签维度</h2>
            <button class="btn btn-ghost btn-xs" title="新建维度" @click="openCreateDimension">
              <span class="material-symbols-outlined icon-sm">add</span>
              新建维度
            </button>
          </div>
          <p class="text-[11px] text-fg-subtle -mt-2">选择维度后，右侧展示该维度的标签树</p>
        </div>

        <div class="px-2 pb-3">
          <div v-if="dimsLoading" class="flex justify-center py-8">
            <span class="loading loading-spinner loading-md text-primary" />
          </div>
          <div v-else-if="dimensions.length === 0" class="px-2 py-8 text-center">
            <div
              class="w-12 h-12 rounded-full bg-base-300/60 flex items-center justify-center mx-auto mb-2"
            >
              <span class="material-symbols-outlined icon-xl text-fg-subtle">account_tree</span>
            </div>
            <p class="text-sm text-fg-muted">暂无标签维度</p>
            <p class="text-xs text-fg-subtle mt-1">点击上方「新建维度」创建第一个维度</p>
          </div>
          <div v-else class="flex flex-col gap-1.5">
            <div
              v-for="d in dimensions"
              :key="d.id"
              class="group flex items-center gap-2 rounded-lg px-3 h-11 cursor-pointer transition-colors"
              :class="selectedDimensionId === d.id ? 'bg-primary/12' : 'hover:bg-base-300/40'"
              @click="selectedDimensionId = d.id"
            >
              <span
                class="material-symbols-outlined icon-sm shrink-0"
                :class="selectedDimensionId === d.id ? 'text-primary' : 'text-fg-subtle'"
              >
                account_tree
              </span>
              <div class="flex-1 min-w-0">
                <p
                  class="text-sm truncate"
                  :class="
                    selectedDimensionId === d.id ? 'text-base-content font-medium' : 'text-fg-muted'
                  "
                >
                  {{ d.name }}
                </p>
                <p v-if="d.description" class="text-[10px] text-fg-subtle truncate">
                  {{ d.description }}
                </p>
              </div>
              <div
                class="flex items-center gap-0.5 shrink-0"
                :class="selectedDimensionId === d.id ? '' : 'hidden group-hover:flex'"
              >
                <button
                  class="btn btn-ghost btn-xs btn-square"
                  title="编辑维度"
                  @click.stop="openEditDimension(d)"
                >
                  <span class="material-symbols-outlined icon-sm text-fg-subtle">edit</span>
                </button>
                <button
                  class="btn btn-ghost btn-xs btn-square hover:bg-error/10"
                  title="删除维度（含标签时后端拒绝）"
                  @click.stop="handleDeleteDimension(d)"
                >
                  <span class="material-symbols-outlined icon-sm text-error">delete</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 右：该维度标签树 + 详情 -->
      <div class="min-w-0 space-y-4">
        <!-- 维度标签树 -->
        <section class="panel p-0" aria-labelledby="tag-tree-title">
          <div class="m-4 flex flex-col gap-3">
            <div class="flex items-center gap-2">
              <h2 id="tag-tree-title" class="section-title m-0">
                {{ selectedDimension?.name ?? '标签树' }}
              </h2>
              <span
                class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-base-300/60 text-fg-muted"
              >
                {{ tagCountByDimension }}
              </span>
              <button
                v-if="hasDimensions"
                class="btn btn-ghost btn-xs ml-auto"
                title="添加子标签（选中节点）"
                :disabled="selectedNode === null"
                @click="selectedNode && openCreateChild(selectedNode)"
              >
                <span class="material-symbols-outlined icon-sm">add</span>
                添加子标签
              </button>
            </div>
            <label class="input flex items-center gap-2">
              <span class="material-symbols-outlined icon-sm text-fg-subtle">search</span>
              <input
                v-model="searchQuery"
                type="text"
                class="w-full bg-transparent"
                placeholder="搜索标签…"
              />
            </label>
          </div>
          <div class="px-2 pb-3 max-h-[300px] overflow-y-auto">
            <div v-if="isLoading" class="flex justify-center py-10">
              <span class="loading loading-spinner loading-md text-primary" />
            </div>
            <TagTree
              v-else
              :tree="tagTree"
              :selected-id="selectedId"
              :search="searchQuery"
              @select="(node) => (selectedId = node.id)"
              @add-child="openCreateChild"
              @edit="openEdit"
              @delete="handleDelete"
            />
          </div>
        </section>

        <!-- 标签详情 -->
        <section class="p-4 panel" aria-labelledby="tag-detail-title">
          <div v-if="!selectedNode" class="py-8 text-center">
            <div
              class="w-14 h-14 rounded-full bg-base-300/60 flex items-center justify-center mx-auto mb-3"
            >
              <span class="material-symbols-outlined icon-2xl text-fg-subtle">label_off</span>
            </div>
            <p class="text-fg-muted text-sm">
              {{ hasDimensions ? '从上方标签树选择一个标签查看详情' : '暂无标签' }}
            </p>
            <p v-if="!hasDimensions" class="text-xs text-fg-subtle mt-1">
              先创建标签维度，再创建标签
            </p>
          </div>

          <div v-else class="space-y-4">
            <div>
              <nav
                class="flex items-center gap-1 text-xs text-fg-subtle mb-2"
                aria-label="标签路径"
              >
                <span class="px-1.5 py-0.5 rounded-full bg-base-300/60 font-mono text-fg-muted">
                  {{ selectedDimension?.name ?? '' }}
                </span>
                <span v-if="selectedPath.length > 0" class="material-symbols-outlined text-sm"
                  >chevron_right</span
                >
                <template v-for="(name, idx) in selectedPath" :key="idx">
                  <span>{{ name }}</span>
                  <span
                    v-if="idx < selectedPath.length - 1"
                    class="material-symbols-outlined text-sm"
                  >
                    chevron_right
                  </span>
                </template>
              </nav>
              <div class="flex items-start justify-between gap-4">
                <div>
                  <h2 id="tag-detail-title" class="text-lg font-semibold text-base-content">
                    {{ selectedNode.name }}
                  </h2>
                  <p v-if="tagDetail?.description" class="text-xs text-fg-subtle mt-1">
                    {{ tagDetail.description }}
                  </p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <button class="btn btn-ghost" @click="openEdit(selectedNode)">
                    <span class="material-symbols-outlined icon-sm">edit</span>
                    编辑
                  </button>
                  <button
                    class="btn btn-ghost btn-sm text-error"
                    @click="handleDelete(selectedNode)"
                  >
                    <span class="material-symbols-outlined icon-sm">delete</span>
                    删除
                  </button>
                </div>
              </div>
            </div>

            <div class="grid grid-cols-3 gap-3">
              <div class="rounded-field bg-base-200/60 border border-base-content/20 px-4 py-3">
                <p class="text-[11px] text-fg-subtle">直接关联资源</p>
                <p class="font-mono text-lg font-semibold text-base-content mt-0.5">
                  {{ resLoading ? '…' : totalCount }}
                  <span class="text-xs font-normal text-fg-subtle">种</span>
                </p>
              </div>
              <div class="rounded-field bg-base-200/60 border border-base-content/20 px-4 py-3">
                <p class="text-[11px] text-fg-subtle">子孙标签</p>
                <p class="font-mono text-lg font-semibold text-base-content mt-0.5">
                  {{ descendantCount }}
                  <span class="text-xs font-normal text-fg-subtle">个</span>
                </p>
              </div>
              <div class="rounded-field bg-base-200/60 border border-base-content/20 px-4 py-3">
                <p class="text-[11px] text-fg-subtle">创建时间</p>
                <p class="font-mono text-lg font-semibold text-base-content mt-0.5">
                  {{ createdDate }}
                </p>
              </div>
            </div>

            <div>
              <div class="flex items-center gap-2 mb-2">
                <h3 class="text-sm font-medium text-base-content">关联资源</h3>
                <span
                  class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-primary/12 text-primary"
                >
                  {{ totalCount }}
                </span>
              </div>

              <div class="panel p-0 overflow-x-auto">
                <table class="table">
                  <thead>
                    <tr>
                      <th>资源名称</th>
                      <th>类别</th>
                      <th>单位</th>
                      <th colspan="2" class="text-center">单价</th>
                      <th colspan="2" class="text-center">碳排放因子</th>
                    </tr>
                  </thead>
                  <tbody>
                    <template v-if="resources.length > 0">
                      <tr
                        v-for="resource in resources"
                        :key="resource.id"
                        class="hover:bg-base-300/30"
                      >
                        <td>
                          <div class="font-medium text-base-content">{{ resource.name }}</div>
                        </td>
                        <td class="text-fg-muted">{{ categoryLabel(resource.category) }}</td>
                        <td class="text-fg-muted">{{ resource.unit }}</td>
                        <td class="table-num w-24 pr-1">
                          <span class="font-num font-medium">{{
                            fmtNumber(resource.unitPrice, 2)
                          }}</span>
                        </td>
                        <td class="w-20 pl-0">
                          <span class="text-neutral-content text-xs">元/{{ resource.unit }}</span>
                        </td>
                        <td class="table-num w-24 pr-1">
                          <span class="font-num">{{ fmtNumber(resource.carbonFactor, 2) }}</span>
                        </td>
                        <td class="w-24 pl-0">
                          <span class="text-neutral-content text-xs text-nowrap"
                            >kg/{{ resource.unit }}</span
                          >
                        </td>
                      </tr>
                    </template>
                    <TableEmptyState
                      v-else
                      :colspan="7"
                      title="暂无直接关联资源"
                      description="在「资源管理 → 打标」中为资源挂载此标签"
                      icon="inventory_2"
                    />
                  </tbody>
                </table>
              </div>

              <PaginationBar
                v-if="totalCount > resPageSize"
                v-model:current="resPage"
                v-model:page-size="resPageSize"
                :total="totalCount"
                class="mt-2"
              />
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- 新建/编辑标签弹窗 -->
    <TagFormModal
      :show="showForm"
      :tree="tagTree"
      :editing-tag="editingTag"
      :default-parent-id="defaultParentId"
      :dimension-id="selectedDimensionId"
      :dimensions="dimensions"
      :editing-description="editingDescription"
      :is-submitting="isSubmitting"
      :error="formError"
      @submit="handleFormSubmit"
      @cancel="closeForm"
    />

    <!-- 新建/编辑维度弹窗 -->
    <BaseModal
      v-model:open="showDimForm"
      :title="editingDimension ? '编辑维度' : '新建维度'"
      class="max-w-md"
      @close="showDimForm = false"
    >
      <form class="space-y-4" @submit.prevent="handleDimensionSubmit">
        <div class="fieldset">
          <label class="fieldset-label">维度名称</label>
          <input
            v-model="dimName"
            class="input"
            :disabled="dimsSubmitting"
            placeholder="如：施工用材、施工运输、施工现场"
            type="text"
          />
        </div>
        <div class="fieldset">
          <label class="fieldset-label">维度描述</label>
          <input
            v-model="dimDescription"
            class="input"
            :disabled="dimsSubmitting"
            placeholder="可选，说明该维度的分类口径"
            type="text"
          />
        </div>
        <div v-if="dimError" class="alert alert-error alert-sm">
          <span class="material-symbols-outlined icon-sm">error</span>
          <span class="text-sm">{{ dimError }}</span>
        </div>
        <div class="modal-action">
          <button
            class="btn btn-ghost"
            type="button"
            :disabled="dimsSubmitting"
            @click="showDimForm = false"
          >
            取消
          </button>
          <button class="btn btn-primary" type="submit" :disabled="dimsSubmitting">
            <span v-if="dimsSubmitting" class="loading loading-spinner loading-xs"></span>
            {{ editingDimension ? '保存' : '创建' }}
          </button>
        </div>
      </form>
    </BaseModal>
  </div>
</template>
