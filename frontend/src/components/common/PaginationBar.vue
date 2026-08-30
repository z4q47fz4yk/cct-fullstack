<script setup lang="ts">
import { computed } from 'vue'
const current = defineModel<number>('current', { default: 1 })
const pageSize = defineModel<number>('pageSize', { default: 10 })
const { total = 0 } = defineProps<{
  total?: number
}>()

const totalPages = computed(() => Math.ceil(total / pageSize.value) || 1)

const pageSizeOptions = [10, 20, 50, 100]

function prevPage() {
  if (current.value > 1) {
    current.value -= 1
  }
}

function nextPage() {
  if (current.value < totalPages.value) {
    current.value += 1
  }
}

function goToPage(page: number) {
  current.value = Math.max(1, Math.min(page, totalPages.value))
}

function onPageSizeChange(event: Event) {
  const value = parseInt((event.target as HTMLSelectElement).value, 10)
  pageSize.value = value
  current.value = 1
}

const startItem = computed(() => (current.value - 1) * pageSize.value + 1)
const endItem = computed(() => Math.min(current.value * pageSize.value, total))

const displayedPages = computed(() => {
  const pages: (number | string)[] = []
  const maxButtons = 5
  const total = totalPages.value

  if (total <= maxButtons) {
    for (let i = 1; i <= total; i++) pages.push(i)
  } else {
    let start = Math.max(1, current.value - 2)
    const end = Math.min(total, start + maxButtons - 1)
    if (end - start < maxButtons - 1) {
      start = Math.max(1, end - maxButtons + 1)
    }
    if (start > 1) {
      pages.push(1)
      if (start > 2) pages.push('...')
    }
    for (let i = start; i <= end; i++) pages.push(i)
    if (end < total) {
      if (end < total - 1) pages.push('...')
      pages.push(total)
    }
  }
  return pages
})
</script>

<template>
  <div class="flex items-center justify-between px-4 py-3">
    <div class="flex items-center gap-4 text-sm text-neutral-content">
      <span>共 {{ total }} 条</span>
      <label class="flex items-center gap-2">
        <span class="text-nowrap">每页</span>
        <select
          class="select select-bordered select-sm"
          :value="pageSize"
          @change="onPageSizeChange"
        >
          <option v-for="opt in pageSizeOptions" :key="opt" :value="opt">
            {{ opt }}
          </option>
        </select>
        <span>条</span>
      </label>
    </div>

    <div class="flex items-center gap-2">
      <button class="btn btn-sm btn-ghost" :disabled="current <= 1" @click="prevPage">
        <span class="material-symbols-outlined icon-sm">chevron_left</span>
      </button>

      <button
        v-for="page in displayedPages"
        :key="page"
        class="btn btn-sm min-w-8"
        :class="page === current ? 'btn-primary' : 'btn-ghost'"
        :disabled="page === '...'"
        @click="typeof page === 'number' && goToPage(page)"
      >
        {{ page }}
      </button>

      <button class="btn btn-sm btn-ghost" :disabled="current >= totalPages" @click="nextPage">
        <span class="material-symbols-outlined icon-sm">chevron_right</span>
      </button>
    </div>
  </div>
</template>

<style lang="css" scoped>
.btn {
  border: 1px solid color-mix(in oklch, var(--color-base-content) 20%, transparent);
}
</style>
