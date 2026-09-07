<script setup lang="ts">
/**
 * TagInput - 表格「标签」列行内编辑控件
 *
 * 取代「点 label 图标 → TagAssignModal 整页勾选」的流程，在单元格内直接：
 * - 悬停后每个非默认 tag chip 尾随 ✕，单击即移除（无二次确认）；
 *   isDefault=true 的系统默认标签（按资源类别自动命中）只读展示、无 ✕；
 * - 虚线 (+tag) chip 始终虚线，悬停与其它 tag 一样高亮；点击浮出
 *   「搜索 + 分组勾选」层，勾选后一次「添加 (N)」整组保存。
 *
 * 交互与视觉约定（AGENTS/设计稿）：
 * - chip 复用只读标签列同款胶囊样式（getSliceColor 位置取色）；
 * - 普通状态 (tag1)(tag2)(+tag)，行悬停后 (tag1 x)(tag2)(+tag)；
 * - 触屏等无 hover 设备上 ✕ 常显；
 * - 保存为单点增删（POST/DELETE /tags/{tag_id}，后端幂等），成功后由
 *   useEntityTagApi 失效实体标签与列表查询自动刷新，不做乐观更新；
 * - 失败 silent + notifyError + console.error，chip 不变（刷新后自洽）。
 */
import { computed, nextTick, ref, watch, onBeforeUnmount } from 'vue'
import type { TagResp } from '@/client/types.gen'
import { useEntityTagApi, type TagEntityRef } from '@/composables/useEntityTagApi'
import { useTagApi } from '@/composables/useTagApi'
import { formatHttpError } from '@/utils/error'
import { notifyError } from '@/composables/useToast'
import { getSliceColor } from '@/utils/themeColors'
import TagPicker from '@/components/tag/TagPicker.vue'

const {
  entity,
  tags,
  disabled = false,
} = defineProps<{
  /** 打标目标实体（resource / task / usage 由 useEntityTagApi 分发） */
  entity: TagEntityRef
  /** 当前行直接挂载的标签（来自列表行数据，随查询失效自动刷新） */
  tags: TagResp[]
  /** 行级只读 / 忙 */
  disabled?: boolean
}>()

const { tags: catalog, isLoading: catalogLoading, error: catalogError, refresh } = useTagApi()
const { addTag, removeTag } = useEntityTagApi()

/** 当前实体 busy：任一单点写请求在途时禁用其它操作，防并发交错 */
const busy = ref(false)

/* ── 行内 chip 渲染 ─────────────────────────────────────── */

const currentIds = computed(() => tags.map((t) => t.id))

/** 悬停删除单个标签：单点 DELETE /tags/{tag_id}（幂等）。
 * 默认标签（isDefault）由系统自动命中，不可手工移除，双重保险。 */
async function removeOne(tag: TagResp) {
  if (busy.value || disabled || tag.isDefault) return
  busy.value = true
  try {
    await removeTag(entity, tag.id)
  } catch (e) {
    notifyError({
      title: '移除标签失败',
      description: formatHttpError(e, '请重试'),
    })
    console.error('Remove tag failed:', e)
  } finally {
    busy.value = false
  }
}

/* ── 新增浮层 ──────────────────────────────────────────── */

const triggerEl = ref<HTMLElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)
const open = ref(false)
const selectedIds = ref<number[]>([])
const panelStyle = ref<{ top: string; left: string }>({ top: '0px', left: '0px' })

/** 可勾选候选：项目目录剔除默认分类标签 + 剔除已挂载标签（与 TagAssignModal 口径一致） */
const assignableCatalog = computed(() => catalog.value.filter((t) => !t.isDefault))
const candidates = computed(() => {
  const attached = new Set(currentIds.value)
  return assignableCatalog.value.filter((t) => !attached.has(t.id))
})

/** 目录非空但全部已挂载 */
const allAttached = computed(
  () =>
    !catalogLoading.value && assignableCatalog.value.length > 0 && candidates.value.length === 0,
)

function openPanel() {
  if (busy.value || disabled) return
  // 已打开时点击 trigger 视为收起
  if (open.value) {
    closePanel()
    return
  }
  selectedIds.value = []
  open.value = true
  nextTick(async () => {
    await positionPanel()
    // 搜索输入自动聚焦
    panelEl.value?.querySelector<HTMLInputElement>('input[type="text"]')?.focus()
  })
}

function closePanel(refocus = true) {
  if (!open.value) return
  open.value = false
  selectedIds.value = []
  if (refocus) triggerEl.value?.focus()
}

async function positionPanel() {
  const trigger = triggerEl.value
  const panel = panelEl.value
  if (!trigger || !panel) return
  const trect = trigger.getBoundingClientRect()
  const prect = panel.getBoundingClientRect()
  const gap = 6
  const margin = 8
  // 下方优先，空间不足向上翻转；左右夹紧在视口内
  let top = trect.bottom + gap
  if (top + prect.height > window.innerHeight - margin && trect.top - gap - prect.height > margin) {
    top = trect.top - gap - prect.height
  } else {
    top = Math.min(top, Math.max(margin, window.innerHeight - prect.height - margin))
  }
  const left = Math.min(
    Math.max(trect.left, margin),
    Math.max(margin, window.innerWidth - prect.width - margin),
  )
  panelStyle.value = { top: `${top}px`, left: `${left}px` }
}

/** 一次保存新增勾选：逐 tag 单点 POST /tags/{tag_id}（幂等、互不依赖） */
async function handleAdd() {
  if (busy.value || disabled || selectedIds.value.length === 0) return
  busy.value = true
  try {
    for (const tagId of selectedIds.value) {
      await addTag(entity, tagId)
    }
    closePanel()
  } catch (e) {
    notifyError({
      title: '添加标签失败',
      description: formatHttpError(e, '请重试'),
    })
    console.error('Add tags failed:', e)
  } finally {
    busy.value = false
  }
}

/* 浮层生命周期：打开时挂 window 监听（Esc / 点外部 / 表格滚动 / 缩放），关闭时解绑 */
function onWindowKeydown(e: Event) {
  const ke = e as KeyboardEvent
  if (ke.key === 'Escape') {
    e.preventDefault()
    closePanel()
  }
}

/** pointerdown 起点不在 trigger / panel 内视为点外部 → 收起 */
function onWindowPointerDown(e: Event) {
  const t = e.target as Node | null
  if (!t) return
  if (triggerEl.value?.contains(t) || panelEl.value?.contains(t)) return
  closePanel(false)
}

function onWindowScrollOrResize() {
  if (open.value) closePanel(false)
}

function detachPanelListeners() {
  window.removeEventListener('keydown', onWindowKeydown)
  window.removeEventListener('pointerdown', onWindowPointerDown)
  window.removeEventListener('scroll', onWindowScrollOrResize, { capture: true })
  window.removeEventListener('resize', onWindowScrollOrResize)
}

watch(open, (isOpen) => {
  if (isOpen) {
    window.addEventListener('keydown', onWindowKeydown)
    window.addEventListener('pointerdown', onWindowPointerDown)
    window.addEventListener('scroll', onWindowScrollOrResize, { capture: true })
    window.addEventListener('resize', onWindowScrollOrResize)
  } else {
    detachPanelListeners()
  }
})

onBeforeUnmount(() => {
  detachPanelListeners()
  open.value = false
})
</script>

<template>
  <!-- ═══ 行内 chip 组 ═══ -->
  <div class="tag-input flex flex-wrap items-center gap-1">
    <span
      v-for="(tag, index) in tags"
      :key="tag.id"
      class="tag-chip inline-flex items-center gap-0.5 h-5 pl-1.5 rounded-full border text-[10px] whitespace-nowrap max-w-full transition-[filter] duration-150 cursor-default"
      :class="[tag.isDefault ? 'pr-1.5' : 'pr-1', busy ? 'opacity-60 pointer-events-none' : '']"
      :style="{
        backgroundColor: `${getSliceColor(index)}14`,
        borderColor: `${getSliceColor(index)}3d`,
      }"
      :title="tag.isDefault ? `${tag.name}（系统默认标签）` : tag.name"
    >
      <span
        class="w-1.5 h-1.5 rounded-full shrink-0"
        :style="{ backgroundColor: getSliceColor(index) }"
      ></span>
      <span class="truncate min-w-0 text-fg-muted">{{ tag.name }}</span>
      <button
        v-if="!tag.isDefault"
        type="button"
        class="remove-btn inline-flex items-center justify-center w-0 h-4 overflow-hidden rounded-full shrink-0 text-fg-subtle hover:text-error hover:bg-base-content/15 active:bg-base-content/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary cursor-pointer transition-[width,opacity,background-color,color] duration-150"
        :disabled="busy || disabled"
        :aria-label="`移除标签 ${tag.name}`"
        :title="`移除标签 ${tag.name}`"
        @click.stop="removeOne(tag)"
      >
        <span class="material-symbols-outlined text-xs leading-none">close</span>
      </button>
    </span>

    <!-- (+标签)：始终虚线，悬停与普通 chip 同样高亮 -->
    <button
      ref="triggerEl"
      type="button"
      class="add-chip inline-flex items-center gap-0.5 h-5 pl-1.5 pr-2 rounded-full border border-dashed border-base-content/40 bg-transparent text-[10px] text-fg-muted hover:bg-base-content/10 hover:text-base-content hover:border-base-content/60 transition-colors cursor-pointer whitespace-nowrap max-w-full"
      :class="{ 'opacity-60 pointer-events-none': busy }"
      :disabled="busy || disabled"
      aria-label="添加标签"
      title="添加标签"
      @click.stop="openPanel"
    >
      <span class="material-symbols-outlined text-xs leading-none">add</span>
      <span class="truncate min-w-0">标签</span>
    </button>

    <span v-if="busy" class="loading loading-spinner loading-xs text-primary shrink-0" />
  </div>

  <!-- ═══ 新增浮层（Teleport 到 body，fixed 定位避免被表格 overflow 裁剪） ═══ -->
  <Teleport to="body">
    <div
      v-if="open"
      ref="panelEl"
      role="dialog"
      aria-label="添加标签"
      class="fixed z-[60] w-72 max-w-[calc(100vw-1rem)] rounded-box bg-base-200 border border-base-content/10 shadow-xl overflow-hidden"
      :style="panelStyle"
    >
      <div class="flex items-center justify-between px-3 py-2 border-b border-base-content/10">
        <span class="text-xs font-medium text-base-content">添加标签</span>
        <button
          type="button"
          class="btn btn-ghost btn-xs btn-square"
          aria-label="关闭"
          @click.stop="closePanel()"
        >
          <span class="material-symbols-outlined text-sm">close</span>
        </button>
      </div>

      <!-- 目录加载/失败 -->
      <div v-if="catalogLoading" class="flex justify-center py-6">
        <span class="loading loading-spinner loading-sm text-primary" />
      </div>
      <div v-else-if="catalogError" class="text-center py-6 px-3">
        <p class="text-xs text-fg-subtle mb-2">标签目录加载失败</p>
        <button type="button" class="btn btn-ghost btn-xs" @click="refresh()">重试</button>
      </div>

      <template v-else>
        <p v-if="allAttached" class="text-center py-6 px-3 text-xs text-fg-subtle">
          已添加该项目的全部标签
        </p>
        <p v-else-if="candidates.length === 0" class="text-center py-6 px-3 text-xs text-fg-subtle">
          项目暂无标签，请先在「碳排放标签」中创建
        </p>

        <!-- 复用 TagPicker：搜索 + 按分组勾选 -->
        <div v-else class="max-h-72 overflow-y-auto px-3 py-2.5 scrollbar-thin">
          <TagPicker v-model="selectedIds" :tags="candidates" :disabled="busy || disabled" />
        </div>

        <div
          class="flex items-center justify-between gap-2 px-3 py-2.5 border-t border-base-content/10"
        >
          <span class="text-[10px] text-fg-subtle">勾选后可一次添加</span>
          <button
            type="button"
            class="btn btn-primary btn-xs gap-1"
            :disabled="busy || disabled || selectedIds.length === 0"
            @click="handleAdd"
          >
            <span v-if="busy" class="loading loading-spinner loading-xs" />
            <template v-else>添加 ({{ selectedIds.length }})</template>
          </button>
        </div>
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
/* ✕ 只在行悬停 / 键盘聚焦到行内时显现（width 0→auto 动画，普通态不占位）；
   触屏等无 hover 设备常显 */
.tag-input .remove-btn {
  opacity: 0;
  pointer-events: none;
}
.tag-input:hover .remove-btn,
.tag-input:focus-within .remove-btn {
  opacity: 1;
  pointer-events: auto;
  width: 1rem;
}
@media (hover: none) {
  .tag-input .remove-btn {
    opacity: 1;
    pointer-events: auto;
    width: 1rem;
  }
}
/* 悬停高亮：与 (+tag) 一致的轻微提亮（颜色来自行内 style，用 filter 统一处理） */
.tag-chip:hover,
.add-chip:hover {
  filter: brightness(1.12);
}
</style>
