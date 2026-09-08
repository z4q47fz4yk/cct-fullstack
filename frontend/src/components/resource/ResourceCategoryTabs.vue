<script setup lang="ts">
/**
 * ResourceCategoryTabs - Category filter tabs 资源分类标签组件
 *
 * - 单选五个分类；`clearable`（默认随 allOption）时点击当前项回到 null（全部）。
 * - `allOption=true` 时在左侧多渲染一个「全部」chip（null=全选，用于列表筛选）。
 * - 模型允许 null；非 clearable 调用方以默认分类起步即可（null 仅作为未选中态）。
 */
import { computed } from 'vue'
import type { ResourceCategory } from '@/types/resource'
import { categoryConfigMap } from '@/types/resource'

const selectedCategory = defineModel<ResourceCategory | null>('selectedCategory')

const {
  disabled = false,
  allOption = false,
  clearable,
} = defineProps<{
  disabled?: boolean
  /** 显示「全部」chip（选中态 = null），用于筛选场景 */
  allOption?: boolean
  /** 点击已选分类是否回到 null；默认跟随 allOption（筛选=true，表单=false） */
  clearable?: boolean
}>()

const canClear = computed(() => clearable ?? allOption)

const categories = computed(() => {
  return Object.entries(categoryConfigMap).map(([key, config]) => ({
    key: key as ResourceCategory,
    ...config,
  }))
})

function selectCategory(category: ResourceCategory) {
  // 点击当前已选分类：clearable 时置 null（全部），否则保持
  if (selectedCategory.value === category && canClear.value) {
    selectedCategory.value = null
    return
  }
  selectedCategory.value = category
}
</script>

<template>
  <div class="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
    <button
      v-if="allOption"
      type="button"
      :disabled="disabled"
      class="btn btn-sm whitespace-nowrap transition-all duration-200"
      :class="{
        'btn-primary': selectedCategory === null,
        'btn-ghost btn-ghost-outline': selectedCategory !== null,
      }"
      aria-label="全部分类"
      @click="selectedCategory = null"
    >
      <span class="material-symbols-outlined icon-sm">select_all</span>
      全部
    </button>

    <button
      v-for="cat in categories"
      type="button"
      :key="cat.key"
      @click="selectCategory(cat.key)"
      :disabled="disabled"
      class="btn btn-sm whitespace-nowrap transition-all duration-200"
      :class="{
        'btn-primary': selectedCategory === cat.key,
        'btn-ghost btn-ghost-outline': selectedCategory !== cat.key,
      }"
    >
      <span class="material-symbols-outlined icon-sm">{{ cat.icon }}</span>
      {{ cat.label }}
    </button>
  </div>
</template>
