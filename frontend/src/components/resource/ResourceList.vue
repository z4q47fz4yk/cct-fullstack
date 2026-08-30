<script setup lang="ts">
/**
 * ResourceList - Resource list container with empty state
 * 资源列表组件
 */
import type { Resource, ResourceCategory } from '@/types/resource'
import ResourceCard from './ResourceCard.vue'

interface Props {
  resources: Resource[]
  category: ResourceCategory
  deletingId?: string | null
}

defineProps<Props>()

defineEmits<{
  (e: 'edit', resource: Resource): void
  (e: 'delete', resource: Resource): void
}>()
</script>

<template>
  <div class="space-y-3">
    <!-- 资源列表 -->
    <template v-if="resources.length > 0">
      <ResourceCard
        v-for="resource in resources"
        :key="resource.id"
        :resource="resource"
        @edit="$emit('edit', resource)"
        @delete="$emit('delete', resource)"
      />
    </template>

    <!-- 空状态 -->
    <div v-else class="panel p-4 border border-primary/10">
      <div class="items-center text-center py-8">
        <div class="w-16 h-16 rounded-full bg-base-300 flex items-center justify-center mb-4">
          <span class="material-symbols-outlined icon-2xl text-base-content/30"> inventory_2 </span>
        </div>
        <h3 class="text-lg font-semibold text-base-content/70">暂无资源</h3>
        <p class="text-sm text-fg-subtle mt-1">该分类下还没有添加资源</p>
      </div>
    </div>
  </div>
</template>
