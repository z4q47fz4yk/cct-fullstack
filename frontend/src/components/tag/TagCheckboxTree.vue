<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TagNodeResp } from '@/client/types.gen'

/**
 * 标签复选树 — 用于图表切片配置（S4）与资源打标（S6）
 *
 * 每个节点独立勾选（勾选父节点 = 整棵子树作为一个切片，勾选子节点 = 子节点独立成片），
 * 不做级联勾选；父节点在"存在已勾选后代但自身未勾选"时显示半选态。
 */
const props = defineProps<{
  tree: TagNodeResp[]
  modelValue: number[]
  search?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [ids: number[]]
}>()

// ─── 展开状态（默认全部展开） ───────────────────────────────

const expandedIds = ref<Set<number>>(new Set())

function collectExpandable(nodes: TagNodeResp[]): number[] {
  const ids: number[] = []
  for (const node of nodes) {
    if ((node.children?.length ?? 0) > 0) {
      ids.push(node.id)
      ids.push(...collectExpandable(node.children ?? []))
    }
  }
  return ids
}

watch(
  () => props.tree,
  (tree) => {
    expandedIds.value = new Set(collectExpandable(tree))
  },
  { immediate: true },
)

function toggleExpand(id: number) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

// ─── 可见行计算（展平 + 展开过滤 + 搜索） ───────────────────

interface TreeRow {
  node: TagNodeResp
  depth: number
  hasChildren: boolean
}

const searchMatched = computed(() => {
  const q = props.search?.trim() ?? ''
  if (!q) return new Map<number, boolean>()
  const map = new Map<number, boolean>()
  function mark(nodes: TagNodeResp[]): boolean {
    let any = false
    for (const node of nodes) {
      const self = node.name.includes(q)
      const child = mark(node.children ?? [])
      const hit = self || child
      map.set(node.id, hit)
      any = any || hit
    }
    return any
  }
  mark(props.tree)
  return map
})

const rows = computed<TreeRow[]>(() => {
  const q = props.search?.trim() ?? ''
  const searching = q.length > 0
  const out: TreeRow[] = []

  function walk(nodes: TagNodeResp[], depth: number, ancestorMatch: boolean) {
    for (const node of nodes) {
      const hasChildren = (node.children?.length ?? 0) > 0
      if (searching) {
        const matched = node.name.includes(q)
        const subtreeHit = searchMatched.value.get(node.id) ?? false
        const show = ancestorMatch || matched || subtreeHit
        if (!show) continue
        out.push({ node, depth, hasChildren })
        if (hasChildren && (matched || subtreeHit)) {
          walk(node.children ?? [], depth + 1, ancestorMatch || matched)
        }
      } else {
        out.push({ node, depth, hasChildren })
        if (hasChildren && expandedIds.value.has(node.id)) {
          walk(node.children ?? [], depth + 1, false)
        }
      }
    }
  }
  walk(props.tree, 0, false)
  return out
})

// ─── 勾选逻辑 ─────────────────────────────────────────────

function isChecked(id: number): boolean {
  return props.modelValue.includes(id)
}

function hasCheckedDescendant(node: TagNodeResp): boolean {
  return (node.children ?? []).some((child) => isChecked(child.id) || hasCheckedDescendant(child))
}

function toggle(node: TagNodeResp) {
  const next = new Set(props.modelValue)
  if (next.has(node.id)) next.delete(node.id)
  else next.add(node.id)
  emit('update:modelValue', [...next])
}
</script>

<template>
  <div class="flex flex-col gap-0.5 w-full">
    <div
      v-for="row in rows"
      :key="row.node.id"
      class="flex items-center gap-2 rounded-lg px-2.5 h-9 transition-colors hover:bg-base-300/40"
      :style="{ paddingLeft: `${8 + row.depth * 18}px` }"
    >
      <button
        type="button"
        class="btn btn-ghost btn-xs btn-square shrink-0 opacity-70"
        :class="{ invisible: !row.hasChildren }"
        :disabled="!row.hasChildren"
        aria-label="展开或折叠"
        @click="toggleExpand(row.node.id)"
      >
        <span
          class="material-symbols-outlined icon-sm text-fg-subtle transition-transform"
          :class="{ '-rotate-90': !expandedIds.has(row.node.id) }"
        >
          keyboard_arrow_down
        </span>
      </button>

      <button
        type="button"
        class="flex items-center justify-center w-4 h-4 rounded shrink-0 border transition-colors"
        :class="
          isChecked(row.node.id)
            ? 'bg-primary border-primary text-primary-content'
            : 'border-fg-subtle/50 hover:border-primary'
        "
        :aria-label="isChecked(row.node.id) ? '取消勾选' : '勾选'"
        @click="toggle(row.node)"
      >
        <span
          v-if="isChecked(row.node.id)"
          class="material-symbols-outlined text-[12px] leading-none"
        >
          check
        </span>
        <span
          v-else-if="hasCheckedDescendant(row.node)"
          class="w-1.5 h-0.5 rounded bg-fg-subtle"
        ></span>
      </button>

      <span
        class="material-symbols-outlined icon-sm shrink-0"
        :style="{ color: row.hasChildren ? 'var(--color-primary)' : 'var(--color-violet)' }"
      >
        {{ row.hasChildren ? 'folder' : 'label' }}
      </span>
      <span
        class="text-sm truncate"
        :class="isChecked(row.node.id) ? 'text-base-content font-medium' : 'text-fg-muted'"
      >
        {{ row.node.name }}
      </span>
    </div>

    <div v-if="rows.length === 0" class="text-center py-6 text-xs text-fg-subtle">
      {{ search ? '未找到匹配的标签' : '暂无标签' }}
    </div>
  </div>
</template>
