<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TagNodeResp } from '@/client/types.gen'
import { countSubtree } from '@/utils/tagTree'

/**
 * 标签树（设置 → 碳排放标签）
 *
 * 支持展开/折叠、搜索过滤（命中分支自动展开）、行级快捷操作与选中态。
 * 行尾徽标显示"子树标签数"（直接关联资源数需按标签查询，见详情面板）。
 */
const props = defineProps<{
  tree: TagNodeResp[]
  selectedId: number | null
  search?: string
}>()

const emit = defineEmits<{
  (e: 'select', node: TagNodeResp): void
  (e: 'add-child', node: TagNodeResp): void
  (e: 'edit', node: TagNodeResp): void
  (e: 'delete', node: TagNodeResp): void
}>()

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

interface TreeRow {
  node: TagNodeResp
  depth: number
  hasChildren: boolean
  descendantCount: number
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
        out.push({
          node,
          depth,
          hasChildren,
          descendantCount: countSubtree(node) - 1,
        })
        if (hasChildren && (matched || subtreeHit)) {
          walk(node.children ?? [], depth + 1, ancestorMatch || matched)
        }
      } else {
        out.push({
          node,
          depth,
          hasChildren,
          descendantCount: countSubtree(node) - 1,
        })
        if (hasChildren && expandedIds.value.has(node.id)) {
          walk(node.children ?? [], depth + 1, false)
        }
      }
    }
  }
  walk(props.tree, 0, false)
  return out
})
</script>

<template>
  <div class="flex flex-col gap-0.5 w-full">
    <div
      v-for="row in rows"
      :key="row.node.id"
      class="group flex items-center gap-1.5 rounded-lg pr-1.5 h-10 cursor-pointer transition-colors"
      :class="selectedId === row.node.id ? 'bg-primary/12' : 'hover:bg-base-300/40'"
      :style="{ paddingLeft: `${6 + row.depth * 18}px` }"
      @click="emit('select', row.node)"
    >
      <button
        type="button"
        class="btn btn-ghost btn-xs btn-square shrink-0 opacity-70"
        :class="{ invisible: !row.hasChildren }"
        :disabled="!row.hasChildren"
        aria-label="展开或折叠"
        @click.stop="toggleExpand(row.node.id)"
      >
        <span
          class="material-symbols-outlined icon-sm text-fg-subtle transition-transform"
          :class="{ '-rotate-90': !expandedIds.has(row.node.id) }"
        >
          keyboard_arrow_down
        </span>
      </button>

      <span
        class="material-symbols-outlined icon-sm shrink-0"
        :style="{
          color: row.hasChildren ? 'var(--color-primary)' : 'var(--color-violet)',
        }"
      >
        {{ row.hasChildren ? 'folder' : 'label' }}
      </span>

      <span
        class="text-sm truncate flex-1 min-w-0"
        :class="selectedId === row.node.id ? 'text-base-content font-medium' : 'text-fg-muted'"
      >
        {{ row.node.name }}
      </span>

      <span
        v-if="row.descendantCount > 0"
        class="shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-primary/12 text-primary"
      >
        {{ row.descendantCount }}
      </span>

      <!-- 行级快捷操作：选中行常显，其余悬停显示 -->
      <div
        class="flex items-center gap-0.5 shrink-0"
        :class="selectedId === row.node.id ? '' : 'hidden group-hover:flex'"
      >
        <button
          type="button"
          class="btn btn-ghost btn-xs btn-square"
          title="添加子标签"
          @click.stop="emit('add-child', row.node)"
        >
          <span class="material-symbols-outlined icon-sm text-fg-subtle">add</span>
        </button>
        <button
          type="button"
          class="btn btn-ghost btn-xs btn-square"
          title="编辑标签"
          @click.stop="emit('edit', row.node)"
        >
          <span class="material-symbols-outlined icon-sm text-fg-subtle">edit</span>
        </button>
        <button
          type="button"
          class="btn btn-ghost btn-xs btn-square hover:bg-error/10"
          title="删除标签"
          @click.stop="emit('delete', row.node)"
        >
          <span class="material-symbols-outlined icon-sm text-error">delete</span>
        </button>
      </div>
    </div>

    <div v-if="rows.length === 0" class="text-center py-6 text-xs text-fg-subtle">
      {{ search ? '未找到匹配的标签' : '暂无标签' }}
    </div>
  </div>
</template>
