<script setup lang="ts" generic="T, V extends string | number | null | undefined">
import { computed, ref, useId, useTemplateRef, watch } from 'vue'
import { onClickOutside } from '@vueuse/core'
import type { SelectOption } from '@/types/select'

defineOptions({ inheritAttrs: false })

const emit = defineEmits<{
  close: []
}>()

const selectedValue = defineModel<V>('selectedValue', { required: true })
const search = defineModel<string>('search', { default: '' })

const {
  options,
  placeholder = '',
  disabled = false,
  id,
} = defineProps<{
  options: SelectOption<T, V>[]
  placeholder?: string
  disabled?: boolean
  id?: string
}>()

/* ── 内部状态 ── */
const open = ref(false)
const highlightedIndex = ref(-1)
const wrapperEl = useTemplateRef('wrapperEl')
const searchInputEl = useTemplateRef('searchInputEl')
const triggerEl = useTemplateRef('triggerEl')
const listboxId = useId()

const activeDescendant = computed(() =>
  highlightedIndex.value >= 0 ? `${listboxId}-option-${highlightedIndex.value}` : undefined,
)

/* ── 展示文本 ── */
const hasValue = computed(() => selectedValue.value != null)

const selectedLabel = computed(() => {
  if (selectedValue.value == null) return ''
  const found = options.find((o) => o.value === selectedValue.value)
  if (!found) return ''
  return found.description ? `${found.label}（${found.description}）` : found.label
})

const triggerText = computed(() => selectedLabel.value || placeholder)

/* ── 行为 ── */
function openDropdown() {
  if (disabled || open.value) return
  open.value = true
  highlightedIndex.value = -1
  setTimeout(() => searchInputEl.value?.focus(), 50)
}

function closeDropdown() {
  if (!open.value) return
  open.value = false
  highlightedIndex.value = -1
  emit('close')
}

function toggleDropdown() {
  return open.value ? closeDropdown() : openDropdown()
}

function handleClear(e: Event) {
  e.stopPropagation()
  selectedValue.value = null as V
  closeDropdown()
  triggerEl.value?.focus()
}

function selectOption(opt: SelectOption<T, V>) {
  if (opt.disabled) return
  selectedValue.value = opt.value
  closeDropdown()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    closeDropdown()
    triggerEl.value?.focus()
    return
  }
  if (!open.value) return

  const len = options.length
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (!len) return
    highlightedIndex.value = highlightedIndex.value < 0 ? 0 : (highlightedIndex.value + 1) % len
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (!len) return
    highlightedIndex.value =
      highlightedIndex.value < 0 ? len - 1 : (highlightedIndex.value - 1 + len) % len
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const opt = options[highlightedIndex.value]
    if (opt) selectOption(opt)
  }
}

/* ── 点击外部收起（vueuse onClickOutside，pointerdown 事件） ── */
onClickOutside(wrapperEl, closeDropdown)

watch(selectedValue, () => {
  if (!hasValue.value) highlightedIndex.value = -1
})
</script>

<template>
  <div ref="wrapperEl" class="relative w-full" v-bind="$attrs">
    <!-- ═══ Trigger ═══ -->
    <button
      ref="triggerEl"
      type="button"
      class="input select select-bordered w-full items-center justify-between"
      :class="{ 'select-disabled': disabled }"
      :id
      :disabled
      :aria-haspopup="'listbox'"
      :aria-expanded="open"
      :aria-controls="listboxId"
      @click="toggleDropdown"
      @keydown="onKeydown"
    >
      <span class="truncate" :class="{ 'opacity-40': !hasValue }">
        {{ triggerText }}
      </span>

      <span class="flex items-center gap-0.5 mr-2">
        <span
          v-if="hasValue"
          role="button"
          tabindex="-1"
          aria-label="清除选择"
          class="btn btn-ghost btn-xs btn-square text-base-content/60 hover:text-error"
          @click.stop="handleClear"
          @keydown.enter.stop.prevent="handleClear"
          @keydown.space.stop.prevent="handleClear"
        >
          <span class="material-symbols-outlined text-base">close</span>
        </span>
      </span>
    </button>

    <!-- ═══ Dropdown ═══ -->
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1.5"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-1.5"
    >
      <div
        v-show="open"
        class="absolute left-0 right-0 z-50 mt-1.5 rounded-box bg-base-200/90 border border-base-content/10 shadow-lg overflow-hidden"
      >
        <!-- Search -->
        <div class="p-2 border-b border-base-content/5">
          <label class="input input-sm flex items-center gap-2 w-full">
            <span class="material-symbols-outlined text-sm opacity-40">search</span>
            <input
              ref="searchInputEl"
              v-model="search"
              type="text"
              class="grow bg-transparent outline-none"
              :placeholder
              :disabled
              autocomplete="off"
              role="searchbox"
              :aria-controls="listboxId"
              :aria-activedescendant="activeDescendant"
              @keydown="onKeydown"
              @click.stop
            />
          </label>
        </div>

        <!-- Options / Empty -->
        <div v-if="options.length === 0" class="p-4 text-center text-sm text-base-content/40">
          没有你想要的
        </div>
        <ul
          v-else
          :id="listboxId"
          role="listbox"
          class="list p-0 max-h-120 overflow-y-auto scrollbar-thin"
        >
          <li
            v-for="(opt, idx) in options"
            :id="`${listboxId}-option-${idx}`"
            :key="opt.value != null ? String(opt.value) : `__ss-${idx}`"
            role="option"
            :aria-selected="opt.value === selectedValue"
            :aria-disabled="opt.disabled || undefined"
            class="list-row rounded-none pt-2 pb-2 flex justify-between"
            :class="{
              active: opt.value === selectedValue,
              'ss-highlighted': highlightedIndex === idx,
              'opacity-40 pointer-events-none': opt.disabled,
            }"
            @mouseenter="highlightedIndex = idx"
            @mousedown.prevent="selectOption(opt)"
          >
            <span class="font-medium opacity-80">{{ opt.label }}</span>
            <span v-if="opt.description" class="text-xs opacity-50">
              {{ opt.description }}
            </span>
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* 键盘高亮态 — DaisyUI menu 没有此概念 */
.ss-highlighted:not(.active) {
  background-color: oklch(from var(--color-base-content) l c h / 0.08);
}

.list-row.active,
.list-row:hover {
  border-left: 2px solid var(--color-primary);
  background-color: oklch(from var(--color-primary) l c h / 0.1);
  span {
    opacity: 1;
  }
}
.list-row.active {
  color: var(--color-primary);
}
</style>
