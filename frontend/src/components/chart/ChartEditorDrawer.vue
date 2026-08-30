<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import VChart from 'vue-echarts'
import { vChartCreate } from '@/client/valibot.gen'
import type { ChartResp, ChartSliceEntity, ResourceCategory } from '@/client/types.gen'
import type { TagNodeResp } from '@/client/types.gen'
import {
  flattenTagTree,
  groupTagTreesByDimension,
  dimensionNameMap,
  dimensionLabel,
} from '@/utils/tagTree'
import { useTagPieChart, type PieSliceDatum } from '@/composables/useTagPieChart'
import { useTagApi } from '@/composables/useTagApi'
import { useTagDimensionApi } from '@/composables/useTagDimensionApi'
import { getSliceColor } from '@/utils/themeColors'
import { categoryConfigMap } from '@/types/resource'
import TagCheckboxTree from '@/components/tag/TagCheckboxTree.vue'

/**
 * 图表编辑抽屉（S4）
 *
 * - 左侧：名称 / 描述 / 切片归属实体（RESOURCE/TASK/USAGE/ANY，附打标位置引导）/
 *         资源分类过滤 / 可选标签树（按维度分组复选）/ 已绑定切片排序列表
 * - 右侧：实时结构预览（保存后按资源用量实时统计）
 * - 保存 = updateChart + setChartTags（标签顺序即 sortOrder）
 */
const props = defineProps<{
  show: boolean
  /** null = 新建 */
  chart: ChartResp | null
  isSubmitting?: boolean
  error?: string
}>()

const emit = defineEmits<{
  (
    e: 'saved',
    payload: {
      name: string
      description: string
      sliceEntity: ChartSliceEntity
      resourceCategories: ResourceCategory[] | null
      tagIds: number[]
    },
  ): void
  (e: 'cancel'): void
}>()

const validationSchema = toTypedSchema(vChartCreate)

const { handleSubmit, resetForm, errors, meta, defineField } = useForm({
  validationSchema,
  initialValues: { name: '', description: '' },
})

const [name, nameAttrs] = defineField('name')
const [description, descriptionAttrs] = defineField('description')

// 标签树（全维度）与维度列表
const { tagTree } = useTagApi()
const { dimensions } = useTagDimensionApi()

// ─── 切片归属实体与资源分类过滤 ────────────────────────────

const SLICE_ENTITY_OPTIONS: {
  value: ChartSliceEntity
  label: string
  hint: string
  icon: string
}[] = [
  { value: 'RESOURCE', label: '资源', hint: '给资源打标：资源管理 → 打标', icon: 'inventory_2' },
  { value: 'TASK', label: '任务', hint: '给任务打标：任务管理 → 打标', icon: 'view_timeline' },
  { value: 'USAGE', label: '用量', hint: '给用量打标：资源使用 → 历史 → 打标', icon: 'edit_note' },
  {
    value: 'ANY',
    label: '任一（资源/任务/用量）',
    hint: '三类实体任一打标均可纳入统计',
    icon: 'hub',
  },
]

const sliceEntity = ref<ChartSliceEntity>('RESOURCE')
const selectedEntityMeta = computed(
  () => SLICE_ENTITY_OPTIONS.find((o) => o.value === sliceEntity.value) ?? SLICE_ENTITY_OPTIONS[0]!,
)

const RESOURCE_CATEGORY_OPTIONS: ResourceCategory[] = [
  'labor',
  'machinery',
  'material',
  'transport',
  'others',
]

const selectedCategories = ref<ResourceCategory[]>([])

function toggleCategory(cat: ResourceCategory) {
  const next = [...selectedCategories.value]
  if (next.includes(cat)) next.splice(next.indexOf(cat), 1)
  else next.push(cat)
  selectedCategories.value = next
}

// ─── 已绑定切片（顺序即 sortOrder） ────────────────────────

const boundTagIds = ref<number[]>([])

const tagNameMap = computed(() => {
  const map = new Map<number, string>()
  for (const row of flattenTagTree(tagTree.value)) map.set(row.node.id, row.node.name)
  return map
})

watch(
  () => props.show,
  (show) => {
    if (!show) return
    const c = props.chart
    resetForm({
      values: {
        name: c?.name ?? '',
        description: c?.description ?? '',
      },
    })
    sliceEntity.value = c?.sliceEntity ?? 'RESOURCE'
    selectedCategories.value = c?.resourceCategories ?? []
    boundTagIds.value = [...(c?.tags ?? [])]
      .sort((a, b) => a.sortOrder - b.sortOrder)
      .map((t) => t.tagId)
  },
)

// 按维度分组的标签树（图表可跨维度绑定切片）
const nameMap = computed(() => dimensionNameMap(dimensions.value))
const groupedTrees = computed(() => groupTagTreesByDimension(tagTree.value))

function onCheckedChange(ids: number[]) {
  // 保持既有顺序：新增的追加到末尾，移除的删除
  const prev = boundTagIds.value
  const removed = prev.filter((id) => !ids.includes(id))
  const added = ids.filter((id) => !prev.includes(id))
  boundTagIds.value = [...prev.filter((id) => !removed.includes(id)), ...added]
}

function moveTag(index: number, delta: number) {
  const next = [...boundTagIds.value]
  const target = index + delta
  if (target < 0 || target >= next.length) return
  ;[next[index], next[target]] = [next[target]!, next[index]!]
  boundTagIds.value = next
}

function removeTag(index: number) {
  const next = [...boundTagIds.value]
  next.splice(index, 1)
  boundTagIds.value = next
}

// ─── 实时预览（结构预览：等分 + 计数） ─────────────────────

const previewSlices = computed<PieSliceDatum[]>(() =>
  boundTagIds.value.map((_, i) => ({
    name: String(i),
    value: 1,
    color: getSliceColor(i),
  })),
)

const { chartOption } = useTagPieChart({
  slices: previewSlices,
  showLegend: false,
  centerTotal: computed(() => String(boundTagIds.value.length)),
  centerLabel: '切片数',
})

const searchQuery = ref('')

// ─── 提交 ──────────────────────────────────────────────────

function onSubmit() {
  emit('saved', {
    name: name.value?.trim() ?? '',
    description: description.value?.trim() ?? '',
    sliceEntity: sliceEntity.value,
    resourceCategories: selectedCategories.value.length > 0 ? [...selectedCategories.value] : null,
    tagIds: boundTagIds.value,
  })
}

const isEditing = computed(() => props.chart !== null)
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-black/60" @click="emit('cancel')"></div>

      <aside
        class="absolute right-0 top-0 h-full w-full max-w-[720px] bg-base-200 border-l border-base-content/20 flex flex-col"
        aria-label="图表编辑器"
      >
        <!-- 头部 -->
        <header class="px-6 pt-5 pb-4 border-b border-base-content/20">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold text-base-content">
                {{ isEditing ? '编辑图表' : '新建图表' }}
              </h2>
              <p class="text-[11px] text-fg-subtle mt-0.5">
                修改切片配置后，饼图数据按资源用量实时统计
              </p>
            </div>
            <button
              class="btn btn-ghost btn-sm btn-square"
              aria-label="关闭"
              @click="emit('cancel')"
            >
              <span class="material-symbols-outlined">close</span>
            </button>
          </div>
        </header>

        <!-- 主体 -->
        <form class="flex-1 min-h-0 flex flex-col" @submit.prevent="handleSubmit(onSubmit)()">
          <div class="flex-1 overflow-y-auto px-6 py-5 space-y-4">
            <div class="fieldset">
              <label class="fieldset-label">图表名称</label>
              <input
                v-model="name"
                v-bind="nameAttrs"
                :disabled="isSubmitting"
                class="input"
                :class="{ 'input-error': errors.name }"
                placeholder="如：施工用材各部分占比"
                type="text"
              />
              <span v-if="errors.name" class="label text-error">{{ errors.name }}</span>
            </div>

            <div class="fieldset">
              <label class="fieldset-label">描述</label>
              <input
                v-model="description"
                v-bind="descriptionAttrs"
                :disabled="isSubmitting"
                class="input"
                placeholder="可选，说明该图表的统计口径"
                type="text"
              />
            </div>

            <!-- 切片归属实体 -->
            <div class="fieldset">
              <label class="fieldset-label">切片归属实体</label>
              <div class="grid grid-cols-2 gap-2">
                <button
                  v-for="opt in SLICE_ENTITY_OPTIONS"
                  :key="opt.value"
                  type="button"
                  class="flex items-center gap-2 px-3 h-10 rounded-field border text-xs transition-colors text-left"
                  :class="
                    sliceEntity === opt.value
                      ? 'bg-primary/12 border-primary/40 text-base-content'
                      : 'bg-base-200/40 border-base-content/20 text-fg-muted hover:border-primary/40'
                  "
                  @click="sliceEntity = opt.value"
                >
                  <span class="material-symbols-outlined icon-sm shrink-0 text-primary">
                    {{ opt.icon }}
                  </span>
                  {{ opt.label }}
                </button>
              </div>
              <p class="text-[11px] text-fg-muted flex items-start gap-1.5 mt-2">
                <span class="material-symbols-outlined icon-sm shrink-0 text-primary">info</span>
                打标位置：{{ selectedEntityMeta.hint }}。选错实体打标会导致饼图数据为 0。
              </p>
            </div>

            <!-- 资源分类过滤（仅 RESOURCE 实体） -->
            <div v-if="sliceEntity === 'RESOURCE'" class="fieldset">
              <label class="fieldset-label">资源分类过滤（可选，不选则统计全部）</label>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="cat in RESOURCE_CATEGORY_OPTIONS"
                  :key="cat"
                  type="button"
                  class="h-7 px-3 rounded-full border text-[11px] transition-colors"
                  :class="
                    selectedCategories.includes(cat)
                      ? 'bg-primary/12 border-primary/40 text-base-content'
                      : 'bg-base-200/40 border-base-content/20 text-fg-muted hover:border-primary/40'
                  "
                  @click="toggleCategory(cat)"
                >
                  {{ categoryConfigMap[cat].label }}
                </button>
              </div>
            </div>

            <!-- 实时预览 -->
            <div
              class="rounded-field bg-primary/5 border border-primary/25 p-4 flex items-center gap-4"
            >
              <div class="w-28 h-28 shrink-0">
                <v-chart :option="chartOption" :autoresize="true" class="w-full h-full" />
              </div>
              <div class="space-y-2 min-w-0">
                <p class="text-xs font-medium text-base-content">实时预览</p>
                <p class="text-[11px] text-fg-muted">
                  切片数量：<span class="font-mono text-base-content">{{
                    boundTagIds.length
                  }}</span>
                </p>
                <p class="text-[11px] text-fg-muted">保存后按资源用量与碳排放因子实时统计</p>
              </div>
            </div>

            <!-- 切片配置 -->
            <div>
              <div class="flex items-center gap-2 mb-2">
                <h3 class="text-sm font-medium text-base-content">切片配置</h3>
                <span
                  class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-primary/12 text-primary"
                >
                  {{ boundTagIds.length }}
                </span>
                <span class="ml-auto text-[11px] text-fg-subtle">顺序即图表展示顺序</span>
              </div>

              <!-- 可选标签（按维度分组，跨维度可重名） -->
              <div class="rounded-field bg-base-200/40 border border-base-content/20 p-3">
                <label class="input flex items-center gap-2 mb-2">
                  <span class="material-symbols-outlined icon-sm text-fg-subtle">search</span>
                  <input
                    v-model="searchQuery"
                    type="text"
                    class="w-full bg-transparent"
                    placeholder="搜索标签…"
                  />
                </label>
                <div class="max-h-56 overflow-y-auto">
                  <template v-if="groupedTrees.length > 0">
                    <div
                      v-for="group in groupedTrees"
                      :key="group.dimensionId"
                      class="mb-3 last:mb-0"
                    >
                      <p
                        class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-base-300/60 text-fg-muted inline-block mb-1"
                      >
                        {{ dimensionLabel(nameMap, group.dimensionId) }}
                      </p>
                      <TagCheckboxTree
                        :tree="group.tree"
                        :model-value="boundTagIds"
                        :search="searchQuery"
                        @update:model-value="onCheckedChange"
                      />
                    </div>
                  </template>
                  <p v-else class="text-center py-6 text-xs text-fg-subtle">
                    暂无标签，请先在「碳排放标签」中创建
                  </p>
                </div>
              </div>

              <!-- 已绑定切片（排序） -->
              <div v-if="boundTagIds.length > 0" class="mt-3 flex flex-col gap-1.5">
                <div
                  v-for="(tagId, index) in boundTagIds"
                  :key="tagId"
                  class="flex items-center gap-2 h-8 px-3 rounded-lg bg-base-200/60 border border-base-content/20"
                >
                  <span class="material-symbols-outlined icon-sm text-fg-subtle shrink-0"
                    >drag_indicator</span
                  >
                  <span
                    class="w-2 h-2 rounded-full shrink-0"
                    :style="{ backgroundColor: getSliceColor(index) }"
                  />
                  <span class="text-xs text-base-content truncate flex-1 min-w-0">
                    {{ tagNameMap.get(tagId) ?? `#${tagId}` }}
                  </span>
                  <button
                    type="button"
                    class="btn btn-ghost btn-xs btn-square"
                    title="上移"
                    :disabled="index === 0"
                    @click="moveTag(index, -1)"
                  >
                    <span class="material-symbols-outlined icon-sm">arrow_upward</span>
                  </button>
                  <button
                    type="button"
                    class="btn btn-ghost btn-xs btn-square"
                    title="下移"
                    :disabled="index === boundTagIds.length - 1"
                    @click="moveTag(index, 1)"
                  >
                    <span class="material-symbols-outlined icon-sm">arrow_downward</span>
                  </button>
                  <button
                    type="button"
                    class="btn btn-ghost btn-xs btn-square hover:bg-error/10"
                    title="移除"
                    @click="removeTag(index)"
                  >
                    <span class="material-symbols-outlined icon-sm text-error">close</span>
                  </button>
                </div>
              </div>
            </div>

            <p class="text-[11px] text-fg-muted leading-relaxed flex items-start gap-1.5">
              <span
                class="material-symbols-outlined icon-sm shrink-0"
                style="color: var(--color-violet)"
                >info</span
              >
              支持跨子树组合切片；打标互斥校验保证同一资源不会在同一图表的多个切片中重复计算。
            </p>

            <div v-if="error" class="alert alert-error alert-sm">
              <span class="material-symbols-outlined icon-sm">error</span>
              <span class="text-sm">{{ error }}</span>
            </div>
          </div>

          <!-- 底部 -->
          <footer
            class="px-6 py-4 border-t border-base-content/20 flex items-center justify-end gap-2"
          >
            <button
              type="button"
              class="btn btn-ghost"
              :disabled="isSubmitting"
              @click="emit('cancel')"
            >
              取消
            </button>
            <button class="btn btn-primary" type="submit" :disabled="isSubmitting || !meta.valid">
              <span v-if="isSubmitting" class="loading loading-spinner loading-xs"></span>
              <span>{{ isEditing ? '保存更改' : '创建图表' }}</span>
            </button>
          </footer>
        </form>
      </aside>
    </div>
  </Teleport>
</template>
