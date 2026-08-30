<script setup lang="ts">
/**
 * ResourceCategoryTabs - Category filter tabs
 * 资源分类标签组件
 */
import { computed } from 'vue'
import type { ResourceCategory } from '@/types/resource'
import { categoryConfigMap } from '@/types/resource'

const selectedCategory = defineModel<ResourceCategory>('selectedCategory')

const { disabled = false } = defineProps<{
  disabled?: boolean
}>()

const categories = computed(() => {
  return Object.entries(categoryConfigMap).map(([key, config]) => ({
    key: key as ResourceCategory,
    ...config,
  }))
})

function selectCategory(category: ResourceCategory) {
  selectedCategory.value = category
}
</script>

<template>
  <div class="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
    <button
      v-for="cat in categories"
      type="button"
      :key="cat.key"
      @click="selectCategory(cat.key)"
      :disabled="disabled"
      class="btn btn-sm whitespace-nowrap transition-all duration-200"
      :class="{
        'btn-primary': selectedCategory === cat.key,
        'btn-ghost btn-ghost-outline': selectedCategory != cat.key,
      }"
    >
      <span class="material-symbols-outlined icon-sm">{{ cat.icon }}</span>
      {{ cat.label }}
    </button>
  </div>
</template>
