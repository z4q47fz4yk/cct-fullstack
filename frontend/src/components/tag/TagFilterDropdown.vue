<script setup lang="ts">
/**
 * TagFilterDropdown - 表格/列表多选标签筛选触发器
 *
 * 复用 TagPicker（自带搜索 + 分组勾选），点外部 / Esc 收起。
 * 语义：AND（命中全部所选），由调用方对结果过滤。
 */
import { nextTick, ref, watch, onBeforeUnmount } from 'vue'
import { onClickOutside } from '@vueuse/core'
import type { TagResp } from '@/client/types.gen'
import TagPicker from '@/components/tag/TagPicker.vue'

const selected = defineModel<number[]>('selected', { default: () => [] })

const { tags, disabled = false } = defineProps<{
  /** 项目内全部标签（含 isDefault 与否由调用方决定） */
  tags: TagResp[]
  disabled?: boolean
}>()

const open = ref(false)
const wrapEl = ref<HTMLElement | null>(null)

onClickOutside(wrapEl, () => (open.value = false))

function toggle() {
  if (disabled) return
  open.value = !open.value
  if (open.value) {
    nextTick(() => {
      wrapEl.value?.querySelector<HTMLInputElement>('input[type="text"]')?.focus()
    })
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    open.value = false
    wrapEl.value?.querySelector('button')?.focus()
  }
}

function clearAll() {
  selected.value = []
}

watch(open, (isOpen) => {
  if (isOpen) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

function labelOf(id: number) {
  return tags.find((t) => t.id === id)?.name ?? `#${id}`
}
</script>

<template>
  <div ref="wrapEl" class="relative">
    <button
      type="button"
      class="btn btn-sm btn-ghost btn-ghost-outline gap-1"
      :class="selected.length > 0 ? '!border-primary/40 !text-primary' : ''"
      :disabled="disabled"
      :aria-expanded="open"
      :aria-haspopup="'listbox'"
      @click="toggle"
    >
      <span class="material-symbols-outlined icon-sm">sell</span>
      <span>标签</span>
      <span v-if="selected.length > 0" class="badge badge-xs badge-primary">
        {{ selected.length }}
      </span>
    </button>

    <!-- 弹层（wrapEl 内 relative 定位；点 wrapEl 外 / Esc 收起） -->
    <div
      v-show="open"
      class="absolute left-0 top-[calc(100%+0.25rem)] z-[60] w-64 rounded-box bg-base-200 border border-base-content/10 shadow-xl overflow-hidden"
      role="listbox"
      aria-label="按标签筛选（需同时包含所选标签）"
    >
      <div v-if="selected.length > 0" class="flex flex-wrap gap-1 px-2.5 pt-2.5">
        <span
          v-for="id in selected"
          :key="id"
          class="inline-flex items-center gap-1 h-5 px-2 rounded-full bg-primary/10 border border-primary/25 text-[10px] text-primary"
        >
          {{ labelOf(id) }}
          <button
            type="button"
            class="inline-flex items-center justify-center w-3 h-3 rounded-full hover:bg-primary/20"
            :aria-label="`移除标签筛选 ${labelOf(id)}`"
            @click="selected = selected.filter((x) => x !== id)"
          >
            <span class="material-symbols-outlined text-[10px] leading-none">close</span>
          </button>
        </span>
        <button
          type="button"
          class="ml-auto text-[10px] text-fg-subtle hover:text-error underline underline-offset-2"
          @click="clearAll"
        >
          清空
        </button>
      </div>

      <div class="max-h-72 overflow-y-auto px-2.5 py-2 scrollbar-thin">
        <TagPicker v-model="selected" :tags="tags" :disabled="disabled" />
      </div>
    </div>
  </div>
</template>
