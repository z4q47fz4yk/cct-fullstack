<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/valibot'
import VChart from 'vue-echarts'
import { vChartCreate } from '@/client/valibot.gen'
import type { ChartResp, SliceResp, TagResp } from '@/client/types.gen'
import { getSliceColor } from '@/utils/themeColors'
import { useTagApi } from '@/composables/useTagApi'
import { useTagPieChart, type PieSliceDatum } from '@/composables/useTagPieChart'

/**
 * 图表编辑抽屉
 *
 * - 左侧：名称 / 描述 / 切片列表（每个切片 = 名称 + 若干标签组）
 * - 组语义：同组标签**且**（须同时命中），不同组之间**或**
 * - 标签可选：项目内全部标签（含「资源类别」默认标签 人工/机械/材料/…，
 *   它们按资源分类自动命中，等效旧版“分类过滤”）
 * - 保存 = updateChart（若编辑）+ setChartSlices（顺序即 sortOrder）
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
      chartType: string
      slices: Array<{ name: string; tags: Array<{ tagId: number; group?: number }> }>
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

// 项目内全部标签（含「资源类别」默认标签，按分组展示）
const { tags } = useTagApi()

/** 所有可选标签项：普通标签 + 默认分类标签（均以真实 tag id 引用） */
const selectable = computed<TagResp[]>(() => tags.value)

const idName = computed(() => {
  const m = new Map<number, string>()
  for (const o of selectable.value) m.set(o.id, o.name)
  return m
})

// ─── 编辑中的切片模型 ─────────────────────────────────────────
// editing: [{ name, groups: [{and: number[]}] }]  groups 之间 or；组内 and
interface EditableSlice {
  name: string
  /** groups: 每组=且；数组元素为组（一组内多个标签且）；组之间或 */
  groups: number[][]
}

const editing = reactive<EditableSlice[]>([])
/** 正在编辑的切片索引（null=收起） */
const expandedSlice = ref<number | null>(null)

function cloneFromResp(slices: SliceResp[] | undefined): EditableSlice[] {
  return (slices ?? []).map((s) => {
    const groups = new Map<number, number[]>()
    for (const t of s.tags ?? []) {
      if (!groups.has(t.group)) groups.set(t.group, [])
      groups.get(t.group)!.push(t.tagId)
    }
    return { name: s.name, groups: [...groups.values()].filter((g) => g.length > 0) }
  })
}

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
    editing.splice(0, editing.length, ...cloneFromResp(c?.slices))
    expandedSlice.value = editing.length > 0 ? 0 : null
  },
)

function addSlice() {
  editing.push({ name: `切片 ${editing.length + 1}`, groups: [[]] })
  expandedSlice.value = editing.length - 1
}

function removeSlice(idx: number) {
  editing.splice(idx, 1)
  expandedSlice.value = null
}

function addGroup(slice: EditableSlice) {
  slice.groups.push([])
}

function removeGroup(slice: EditableSlice, gi: number) {
  slice.groups.splice(gi, 1)
  if (slice.groups.length === 0) slice.groups.push([])
}

function isTagInSlice(slice: EditableSlice, tagId: number): boolean {
  return slice.groups.some((g) => g.includes(tagId))
}

function toggleTagInSlice(slice: EditableSlice, tagId: number) {
  // 打标到第一组（且组）；若已在则移除
  if (isTagInSlice(slice, tagId)) {
    for (const g of slice.groups) {
      const i = g.indexOf(tagId)
      if (i >= 0) g.splice(i, 1)
    }
  } else {
    slice.groups[0]!.push(tagId)
  }
}

function removeTagFromGroup(slice: EditableSlice, gi: number, idx: number) {
  slice.groups[gi]!.splice(idx, 1)
}

function moveSlice(idx: number, delta: number) {
  const target = idx + delta
  if (target < 0 || target >= editing.length) return
  const tmp = editing[idx]!
  editing.splice(idx, 1)
  editing.splice(target, 0, tmp)
  expandedSlice.value = target
}

// 实时预览
const previewSlices = computed<PieSliceDatum[]>(() =>
  editing.map((_, i) => ({ name: String(i), value: 1, color: getSliceColor(i) })),
)

const { chartOption } = useTagPieChart({
  slices: previewSlices,
  showLegend: false,
  centerTotal: computed(() => String(editing.length)),
  centerLabel: '切片数',
})

const sliceHasError = computed(() =>
  editing.some((s) => !s.name.trim() || s.groups.every((g) => g.length === 0)),
)

// ─── 提交 ──────────────────────────────────────────────────────
function toSliceUpsert(s: EditableSlice) {
  const tagsItems: Array<{ tagId: number; group: number }> = []
  s.groups.forEach((g, gi) => {
    for (const tagId of g) tagsItems.push({ tagId, group: gi })
  })
  return { name: s.name.trim(), tags: tagsItems }
}

function onSubmit() {
  if (sliceHasError.value) return
  emit('saved', {
    name: name.value?.trim() ?? '',
    description: description.value?.trim() ?? '',
    chartType: 'PIE',
    slices: editing.map(toSliceUpsert),
  })
}

const isEditing = computed(() => props.chart !== null)
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-black/60" @click="emit('cancel')"></div>

      <aside
        class="absolute right-0 top-0 h-full w-full max-w-[760px] bg-base-200 border-l border-base-content/20 flex flex-col"
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
                切片 = 一组标签；同组标签需同时命中（且），不同组命中任一（或）即可
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
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
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
            </div>

            <!-- 实时预览 -->
            <div
              class="rounded-field bg-primary/5 border border-primary/25 p-4 flex items-center gap-4"
            >
              <div class="w-24 h-24 shrink-0">
                <v-chart :option="chartOption" :autoresize="true" class="w-full h-full" />
              </div>
              <div class="space-y-1 min-w-0">
                <p class="text-xs font-medium text-base-content">实时预览</p>
                <p class="text-[11px] text-fg-muted">
                  切片数量：<span class="font-mono text-base-content">{{ editing.length }}</span>
                </p>
                <p class="text-[11px] text-fg-muted">保存后按资源用量与碳排放因子统计</p>
              </div>
            </div>

            <!-- 切片配置列表 -->
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <h3 class="text-sm font-medium text-base-content">切片配置</h3>
                <button type="button" class="btn btn-ghost btn-xs" @click="addSlice">
                  <span class="material-symbols-outlined icon-sm">add</span>
                  添加切片
                </button>
              </div>

              <div
                v-if="editing.length === 0"
                class="text-center py-8 text-xs text-fg-subtle panel"
              >
                尚未配置切片 —— 点击「添加切片」配置第一个
              </div>

              <div
                v-for="(slice, idx) in editing"
                :key="idx"
                class="panel p-3 flex flex-col gap-2"
                :class="{ 'border-error/60': !slice.name.trim() }"
              >
                <div class="flex items-center gap-2">
                  <span
                    class="w-6 h-6 rounded-full text-center text-[11px] leading-6 font-mono shrink-0"
                    :style="{
                      backgroundColor: `${getSliceColor(idx)}22`,
                      color: getSliceColor(idx),
                    }"
                  >
                    {{ idx + 1 }}
                  </span>
                  <input
                    v-model="slice.name"
                    class="input input-sm flex-1 min-w-0"
                    placeholder="切片名称（饼图扇区名）"
                  />
                  <button
                    type="button"
                    class="btn btn-ghost btn-xs btn-square"
                    title="上移"
                    :disabled="idx === 0"
                    @click="moveSlice(idx, -1)"
                  >
                    <span class="material-symbols-outlined icon-sm">arrow_upward</span>
                  </button>
                  <button
                    type="button"
                    class="btn btn-ghost btn-xs btn-square"
                    title="下移"
                    :disabled="idx === editing.length - 1"
                    @click="moveSlice(idx, 1)"
                  >
                    <span class="material-symbols-outlined icon-sm">arrow_downward</span>
                  </button>
                  <button
                    type="button"
                    class="btn btn-ghost btn-xs btn-square hover:bg-error/10"
                    title="删除切片"
                    @click="removeSlice(idx)"
                  >
                    <span class="material-symbols-outlined icon-sm text-error">delete</span>
                  </button>
                </div>

                <!-- 组（或/且） -->
                <div class="flex flex-col gap-1.5">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-[10px] text-fg-subtle">命中规则：</span>
                    <span
                      v-for="(group, gi) in slice.groups"
                      :key="gi"
                      class="text-[10px] font-mono px-1.5 py-0.5 rounded-full"
                      :class="
                        gi === 0 ? 'bg-primary/12 text-primary' : 'bg-violet-500/10 text-violet-400'
                      "
                    >
                      {{ gi === 0 ? '且' : '或' }}-{{ gi + 1 }}
                    </span>
                  </div>

                  <div
                    v-for="(group, gi) in slice.groups"
                    :key="gi"
                    class="rounded-field bg-base-200/40 border border-base-content/20 p-2"
                  >
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-[11px] font-medium text-fg-muted">
                        {{
                          gi === 0 ? '必须同时命中以下标签（且组）' : '或 命中以下任一组内全部标签'
                        }}
                      </span>
                      <button
                        v-if="gi > 0"
                        type="button"
                        class="btn btn-ghost btn-xs"
                        title="删除该或组"
                        @click="removeGroup(slice, gi)"
                      >
                        移除该或组
                      </button>
                    </div>
                    <div class="flex flex-wrap gap-1.5">
                      <span
                        v-for="(tagId, ti) in group"
                        :key="tagId"
                        class="inline-flex items-center gap-1 h-6 pl-2 pr-1 rounded-full bg-primary/10 border border-primary/30 text-[11px]"
                      >
                        {{ idName.get(tagId) ?? `#${tagId}` }}
                        <button
                          type="button"
                          class="btn btn-ghost btn-xs btn-square h-4 min-h-4 w-4"
                          title="移除标签"
                          @click="removeTagFromGroup(slice, gi, ti)"
                        >
                          <span class="material-symbols-outlined text-[11px]">close</span>
                        </button>
                      </span>
                      <span v-if="group.length === 0" class="text-[11px] text-fg-subtle">
                        尚未选择标签
                      </span>
                    </div>
                  </div>

                  <div class="flex items-center gap-2">
                    <button
                      v-if="slice.groups.length < 3"
                      type="button"
                      class="btn btn-ghost btn-xs text-violet-400"
                      @click="addGroup(slice)"
                    >
                      <span class="material-symbols-outlined icon-sm">add</span>
                      添加或组（命中任一即可）
                    </button>
                  </div>

                  <!-- 标签选择（加入第一且组） -->
                  <div
                    class="rounded-field bg-base-200/40 border border-base-content/20 p-2 max-h-44 overflow-y-auto"
                  >
                    <p class="text-[10px] text-fg-subtle mb-1">
                      点击标签加入该切片（第一组即「且组」；已加入的标签点击可移除）
                    </p>
                    <div class="flex flex-wrap gap-1.5">
                      <button
                        v-for="opt in selectable"
                        :key="opt.id"
                        type="button"
                        class="h-6 px-2 rounded-full border text-[11px] transition-colors"
                        :class="
                          isTagInSlice(slice, opt.id)
                            ? 'bg-primary/15 border-primary/50 text-base-content'
                            : 'bg-base-200/40 border-base-content/20 text-fg-muted hover:border-primary/40'
                        "
                        @click="toggleTagInSlice(slice, opt.id)"
                      >
                        {{ opt.name }}<template v-if="opt.isDefault">（默认）</template>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <p class="text-[11px] text-fg-muted leading-relaxed flex items-start gap-1.5">
              <span class="material-symbols-outlined icon-sm shrink-0 text-primary">info</span>
              「资源类别」默认标签（如「材料」）按资源分类自动命中（材料=所有材料类
              资源），可与普通标签混用「且/或」组合。
              多条用量命中同一图表多个切片时会重复计入（可在「数据体检」检查重叠）。
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
            <button
              class="btn btn-primary"
              type="submit"
              :disabled="isSubmitting || !meta.valid || sliceHasError"
            >
              <span v-if="isSubmitting" class="loading loading-spinner loading-xs"></span>
              <span>{{ isEditing ? '保存更改' : '创建图表' }}</span>
            </button>
          </footer>
        </form>
      </aside>
    </div>
  </Teleport>
</template>
