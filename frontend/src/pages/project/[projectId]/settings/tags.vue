<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuery } from '@pinia/colada'
import { useTagApi, useTagGroups, useTagResources } from '@/composables/useTagApi'
import { useProjectContext } from '@/composables/useProjectContext'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { formatHttpError } from '@/utils/error'
import BaseModal from '@/components/ui/BaseModal.vue'
import { getTagQuery } from '@/client/@pinia/colada.gen'
import type { TagGroupResp, TagResp } from '@/client/types.gen'
import type { ResourceCategory } from '@/types/resource'
import { categoryConfigMap } from '@/types/resource'
import { UNGROUPED_LABEL, filterTags } from '@/utils/tagGroup'
import ErrorState from '@/components/common/ErrorState.vue'
import PaginationBar from '@/components/common/PaginationBar.vue'
import TableEmptyState from '@/components/common/TableEmptyState.vue'
import { fmtNumber } from '@/utils/format'

definePage({
  meta: {
    title: '碳排放标签',
    description: '扁平标签 + 展示分组管理，标签名称项目内唯一',
    icon: 'label',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 7,
  },
})

const { tags, isLoading, error, refresh, createTag, updateTag, deleteTag, isSubmitting } =
  useTagApi()
const { groups, refresh: refreshGroups } = useTagGroups()
const { currentProjectId } = useProjectContext()
const { confirmDanger } = useConfirm()
const { notifySuccess, notifyWarning } = useToast()

// ─── 左侧：分组列表 ────────────────────────────────────────

const selectedGroup = ref<string | null>(null)

watch(
  () => groups.value,
  (list) => {
    if (selectedGroup.value !== null && !list.some((g) => g.group === selectedGroup.value)) {
      selectedGroup.value = null // 未知分组 → 全部
    }
  },
  { immediate: true },
)

const visibleTags = computed<TagResp[]>(() => {
  const base = tags.value
  if (selectedGroup.value === null) return filterTags(base, searchQuery.value)
  return filterTags(
    base.filter((t) => (t.group ?? '') === selectedGroup.value),
    searchQuery.value,
  )
})

// ─── 右侧选中标签 ───────────────────────────────────────────

const selectedId = ref<number | null>(null)

const selectedTag = computed<TagResp | null>(() => {
  const tag = tags.value.find((t) => t.id === selectedId.value) ?? null
  // 搜索 / 分组过滤后选中项已不在可见列表时，右侧显示空态，
  // 避免"搜索无结果却仍展示上一次选中的标签"的误导
  if (tag && !visibleTags.value.some((t) => t.id === tag.id)) return null
  return tag
})

// 有选中记录、但已被搜索 / 分组过滤隐藏（右侧应显示"未选中标签"空态）
const hiddenSelection = computed(() => selectedId.value !== null && selectedTag.value === null)

const { state: tagDetailState } = useQuery(() => ({
  ...getTagQuery({
    path: { project_id: currentProjectId.value!, id: selectedId.value! },
  }),
  enabled: selectedId.value !== null,
}))
const tagDetail = computed(() => tagDetailState.value?.data)

// 关联资源（分页）
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

const createdDate = computed(() => tagDetail.value?.createdAt?.slice(0, 10) ?? '—')

// ─── 搜索 ──────────────────────────────────────────────────
const searchQuery = ref('')

// ─── 表单弹窗 ──────────────────────────────────────────────
const showForm = ref(false)
const editingTag = ref<TagResp | null>(null)
const formName = ref('')
const formGroup = ref('')
const formDescription = ref('')
const formError = ref('')

const groupSuggestions = computed(() => {
  const set = new Set(groups.value.map((g) => g.group).filter((g) => g !== ''))
  for (const t of tags.value) if (t.group) set.add(t.group)
  return [...set]
})

function openCreate(group = '') {
  editingTag.value = null
  formName.value = ''
  formGroup.value = group
  formDescription.value = ''
  formError.value = ''
  showForm.value = true
}

function openEdit(tag: TagResp) {
  if (tag.isDefault) {
    notifyWarning('默认标签由系统生成，不允许编辑')
    return
  }
  editingTag.value = tag
  formName.value = tag.name
  formGroup.value = tag.group ?? ''
  formDescription.value = tag.description ?? ''
  formError.value = ''
  showForm.value = true
}

async function handleFormSubmit() {
  const name = formName.value.trim()
  if (!name) {
    formError.value = '请输入标签名称'
    return
  }
  formError.value = ''
  try {
    if (editingTag.value) {
      await updateTag({
        path: { project_id: currentProjectId.value!, id: editingTag.value.id },
        body: { name, group: formGroup.value, description: formDescription.value.trim() },
      })
      notifySuccess('标签已更新')
    } else {
      await createTag({
        path: { project_id: currentProjectId.value! },
        body: { name, group: formGroup.value, description: formDescription.value.trim() },
      })
      notifySuccess('标签已创建')
    }
    showForm.value = false
  } catch (e) {
    formError.value = formatHttpError(e, '保存失败，请重试')
  }
}

// ─── 删除 ──────────────────────────────────────────────────
async function handleDelete(tag: TagResp) {
  if (tag.isDefault) {
    // 默认标签由系统在项目创建时写入，应用层禁止删除。
    notifyWarning('默认标签由系统生成，不允许删除')
    return
  }
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

function groupLabel(group: string): string {
  return group === '' ? UNGROUPED_LABEL : group
}

function categoryLabel(category: ResourceCategory): string {
  return categoryConfigMap[category]?.label ?? category
}

const groupCount = (g: TagGroupResp): number => g.count
</script>

<template>
  <Teleport defer to="#header-actions">
    <button class="btn btn-primary gap-1 px-5" :disabled="isLoading" @click="openCreate()">
      <span class="material-symbols-outlined icon-sm">add</span>
      添加标签
    </button>
  </Teleport>

  <ErrorState
    v-if="error"
    title="加载失败"
    description="无法获取标签列表，请检查网络连接"
    @retry="refresh"
  />

  <div v-else class="space-y-4">
    <!-- 汇总说明 -->
    <section class="panel px-4 py-3 flex items-center gap-3">
      <span class="material-symbols-outlined text-primary icon-md shrink-0">label</span>
      <p class="text-xs text-fg-muted leading-relaxed">
        标签为扁平结构，名称在项目内唯一；「分组」仅用于列表/选择器分组展示，不参与碳排放统计。
        资源、任务、用量分别打标，饼图按其标签命中统计。 项目创建时系统会写入「默认」标签（如
        人工/机械/材料/运输/其他），它们仅供识别，不允许编辑或删除。
      </p>
    </section>

    <div class="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4 items-start">
      <!-- 左：分组列表 -->
      <section class="panel p-0" aria-labelledby="group-list-title">
        <div class="m-4 flex flex-col gap-2">
          <h2 id="group-list-title" class="section-title m-0">标签分组</h2>
          <p class="text-[11px] text-fg-subtle -mt-1">选择分组后右侧仅显示该分组标签</p>
        </div>
        <div class="px-2 pb-3 flex flex-col gap-1">
          <div
            class="flex items-center justify-between px-3 h-10 rounded-lg cursor-pointer transition-colors"
            :class="selectedGroup === null ? 'bg-primary/12' : 'hover:bg-base-300/40'"
            @click="selectedGroup = null"
          >
            <span
              class="text-sm"
              :class="selectedGroup === null ? 'text-base-content font-medium' : 'text-fg-muted'"
            >
              全部标签
            </span>
            <span class="text-[10px] font-mono text-fg-muted">{{ tags.length }}</span>
          </div>
          <div
            v-for="g in groups"
            :key="g.group"
            class="flex items-center justify-between px-3 h-10 rounded-lg cursor-pointer transition-colors"
            :class="selectedGroup === g.group ? 'bg-primary/12' : 'hover:bg-base-300/40'"
            @click="selectedGroup = g.group"
          >
            <span
              class="text-sm truncate"
              :class="selectedGroup === g.group ? 'text-base-content font-medium' : 'text-fg-muted'"
            >
              {{ groupLabel(g.group) }}
            </span>
            <span class="text-[10px] font-mono text-fg-muted">{{ groupCount(g) }}</span>
          </div>
        </div>
      </section>

      <!-- 右：标签列表 + 详情 -->
      <div class="min-w-0 space-y-4">
        <section class="panel p-0" aria-labelledby="tag-list-title">
          <div class="m-4 flex flex-col gap-2">
            <div class="flex items-center gap-2">
              <h2 id="tag-list-title" class="section-title m-0">
                {{ selectedGroup === null ? '全部标签' : groupLabel(selectedGroup) }}
              </h2>
              <span
                class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-base-300/60 text-fg-muted"
              >
                {{ visibleTags.length }}
              </span>
              <button
                v-if="selectedGroup !== null"
                class="btn btn-ghost btn-xs ml-auto"
                @click="openCreate(selectedGroup === UNGROUPED_LABEL ? '' : selectedGroup)"
              >
                <span class="material-symbols-outlined icon-sm">add</span>
                添加到此分组
              </button>
            </div>
            <label class="input flex items-center gap-2">
              <span class="material-symbols-outlined icon-sm text-fg-subtle">search</span>
              <input
                v-model="searchQuery"
                type="text"
                class="w-full bg-transparent"
                placeholder="搜索标签名称或分组…"
              />
            </label>
          </div>

          <div class="px-2 pb-3 max-h-[380px] overflow-y-auto">
            <div v-if="isLoading" class="flex justify-center py-10">
              <span class="loading loading-spinner loading-md text-primary" />
            </div>
            <div v-else-if="visibleTags.length === 0" class="text-center py-10">
              <span class="material-symbols-outlined icon-2xl text-fg-subtle">label_off</span>
              <p class="text-sm text-fg-muted mt-2">
                {{ searchQuery ? '未找到匹配的标签' : '暂无标签' }}
              </p>
              <p class="text-xs text-fg-subtle mt-1">点击右上角「添加标签」创建第一个标签</p>
            </div>
            <div v-else class="flex flex-col gap-0.5">
              <div
                v-for="tag in visibleTags"
                :key="tag.id"
                class="group flex items-center gap-2 rounded-lg px-3 h-10 cursor-pointer transition-colors"
                :class="selectedId === tag.id ? 'bg-primary/12' : 'hover:bg-base-300/40'"
                @click="selectedId = tag.id"
              >
                <span
                  class="material-symbols-outlined icon-sm shrink-0"
                  :class="selectedId === tag.id ? 'text-primary' : 'text-fg-subtle'"
                >
                  label
                </span>
                <div class="flex-1 min-w-0">
                  <p
                    class="text-sm truncate"
                    :class="
                      selectedId === tag.id ? 'text-base-content font-medium' : 'text-fg-muted'
                    "
                  >
                    {{ tag.name }}
                  </p>
                  <p v-if="tag.group" class="text-[10px] text-fg-subtle truncate">
                    {{ tag.group }}
                  </p>
                </div>
                <span
                  v-if="tag.isDefault"
                  class="shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-primary/12 text-primary"
                  title="项目级默认标签，由系统在项目创建时生成，不允许编辑/删除"
                >
                  默认
                </span>
                <div
                  v-if="!tag.isDefault"
                  class="flex items-center gap-0.5 shrink-0"
                  :class="selectedId === tag.id ? '' : 'hidden group-hover:flex'"
                >
                  <button
                    class="btn btn-ghost btn-xs btn-square"
                    title="编辑标签"
                    @click.stop="openEdit(tag)"
                  >
                    <span class="material-symbols-outlined icon-sm text-fg-subtle">edit</span>
                  </button>
                  <button
                    class="btn btn-ghost btn-xs btn-square hover:bg-error/10"
                    title="删除标签"
                    @click.stop="handleDelete(tag)"
                  >
                    <span class="material-symbols-outlined icon-sm text-error">delete</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 标签详情 -->
        <section class="panel p-4" aria-labelledby="tag-detail-title">
          <div v-if="!selectedTag" class="py-8 text-center">
            <div
              class="w-14 h-14 rounded-full bg-base-300/60 flex items-center justify-center mx-auto mb-3"
            >
              <span class="material-symbols-outlined icon-2xl text-fg-subtle">label_off</span>
            </div>
            <p class="text-fg-muted text-sm">
              {{ hiddenSelection ? '未选中标签' : '从左侧选择一个标签查看详情' }}
            </p>
            <p v-if="hiddenSelection" class="text-xs text-fg-subtle mt-1">
              当前搜索或分组下没有匹配结果，请调整关键词后重新选择标签
            </p>
          </div>
          <div v-else class="space-y-4">
            <div>
              <span
                class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-base-300/60 text-fg-muted"
              >
                {{ groupLabel(selectedTag.group ?? '') }}
              </span>
              <div class="flex items-start justify-between gap-4 mt-1">
                <div>
                  <div class="flex items-center gap-2">
                    <h2 id="tag-detail-title" class="text-lg font-semibold text-base-content">
                      {{ selectedTag.name }}
                    </h2>
                    <span
                      v-if="selectedTag.isDefault"
                      class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-primary/12 text-primary"
                    >
                      默认
                    </span>
                  </div>
                  <p v-if="selectedTag.description" class="text-xs text-fg-subtle mt-1">
                    {{ selectedTag.description }}
                  </p>
                  <p v-if="selectedTag.isDefault" class="text-xs text-fg-subtle mt-1">
                    该标签由系统在项目创建时生成，禁止修改或删除。
                  </p>
                </div>
                <div v-if="!selectedTag.isDefault" class="flex items-center gap-2 shrink-0">
                  <button class="btn btn-ghost" @click="openEdit(selectedTag)">
                    <span class="material-symbols-outlined icon-sm">edit</span>
                    编辑
                  </button>
                  <button
                    class="btn btn-ghost btn-sm text-error"
                    @click="handleDelete(selectedTag)"
                  >
                    <span class="material-symbols-outlined icon-sm">delete</span>
                    删除
                  </button>
                </div>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div class="rounded-field bg-base-200/60 border border-base-content/20 px-4 py-3">
                <p class="text-[11px] text-fg-subtle">直接关联资源</p>
                <p class="font-mono text-lg font-semibold text-base-content mt-0.5">
                  {{ resLoading ? '…' : totalCount }}
                  <span class="text-xs font-normal text-fg-subtle">种</span>
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
    <BaseModal
      v-model:open="showForm"
      :title="editingTag ? '编辑标签' : '新建标签'"
      class="max-w-md"
      @close="showForm = false"
    >
      <form class="space-y-4" @submit.prevent="handleFormSubmit">
        <div class="fieldset">
          <label class="fieldset-label">标签名称</label>
          <input v-model="formName" class="input" placeholder="如：商品混凝土" type="text" />
        </div>
        <div class="fieldset">
          <label class="fieldset-label">展示分组</label>
          <input
            v-model="formGroup"
            class="input"
            list="group-suggestions"
            placeholder="如：材料 / 运输（留空=未分组）"
            type="text"
          />
          <datalist id="group-suggestions">
            <option v-for="g in groupSuggestions" :key="g" :value="g" />
          </datalist>
          <span class="text-xs text-fg-subtle">分组仅用于界面归类展示，可自由填写</span>
        </div>
        <div class="fieldset">
          <label class="fieldset-label">描述</label>
          <input v-model="formDescription" class="input" placeholder="可选" type="text" />
        </div>
        <div v-if="formError" class="alert alert-error alert-sm">
          <span class="material-symbols-outlined icon-sm">error</span>
          <span class="text-sm">{{ formError }}</span>
        </div>
        <div class="modal-action">
          <button class="btn btn-ghost" type="button" @click="showForm = false">取消</button>
          <button class="btn btn-primary" type="submit" :disabled="isSubmitting">
            <span v-if="isSubmitting" class="loading loading-spinner loading-xs"></span>
            {{ editingTag ? '保存' : '创建' }}
          </button>
        </div>
      </form>
    </BaseModal>
  </div>
</template>
