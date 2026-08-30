<script setup lang="ts">
import { computed } from 'vue'
import type { ResourceCategoryStat, ResourceCategory } from '@/client/types.gen'
import { categoryConfigMap } from '@/types/resource'
import { getCategoryColor } from '@/utils/themeColors'

const { stats, loading = false } = defineProps<{
  stats: ResourceCategoryStat[]
  loading?: boolean
}>()

const categories: ResourceCategory[] = ['labor', 'machinery', 'material', 'transport', 'others']

const statsMap = computed(() => {
  const map = new Map<ResourceCategory, number>()
  stats.forEach((stat) => {
    map.set(stat.category, stat.count)
  })
  return map
})

function getCount(category: ResourceCategory): number {
  return statsMap.value.get(category) ?? 0
}

function categoryBg(category: ResourceCategory): string {
  return `color-mix(in oklch, ${getCategoryColor(category)} 10%, transparent)`
}

function categoryText(category: ResourceCategory): string {
  return getCategoryColor(category)
}
</script>

<template>
  <div class="grid grid-cols-4 gap-4">
    <div
      v-for="category in categories"
      :key="category"
      class="card"
      :style="{ backgroundColor: categoryBg(category) }"
    >
      <div class="py-4 px-5 flex-row items-center justify-between">
        <div>
          <p class="text-sm opacity-70">{{ categoryConfigMap[category].label }}</p>
          <p v-if="loading" class="loading loading-spinner loading-sm"></p>
          <p v-else class="text-2xl font-bold font-num">{{ getCount(category) }}</p>
        </div>
        <div
          class="w-12 h-12 rounded-xl flex items-center justify-center"
          :style="{ backgroundColor: categoryBg(category) }"
        >
          <span
            class="material-symbols-outlined icon-xl"
            :style="{ color: categoryText(category) }"
          >
            {{ categoryConfigMap[category].icon }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
