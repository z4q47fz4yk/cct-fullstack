<script setup lang="ts">
/**
 * ResourceCard - Individual resource display card
 * 资源卡片组件
 */
import { computed } from 'vue'
import type { Resource } from '@/types/resource'
import { categoryConfigMap } from '@/types/resource'
import { fmtNumber } from '@/utils/format'

const { resource } = defineProps<{ resource: Resource }>()

defineEmits<{
  (e: 'edit', resource: Resource): void
  (e: 'delete', resource: Resource): void
}>()

const categoryIcon = computed(() => {
  return categoryConfigMap[resource.category].icon
})
</script>

<template>
  <div class="panel panel-hover p-4 group">
    <div class="flex flex-col">
      <div class="flex items-start gap-3">
        <!-- 资源图标 -->
        <div class="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined text-primary icon-lg">
            {{ categoryIcon }}
          </span>
        </div>

        <!-- 资源信息 -->
        <div class="flex-1 min-w-0">
          <div class="flex items-start justify-between gap-2">
            <div>
              <h3 class="font-semibold text-base-content truncate">
                {{ resource.name }}
              </h3>
            </div>
            <!-- 操作按钮 -->
            <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button @click="$emit('edit', resource)" class="btn btn-ghost btn-xs btn-square">
                <span class="material-symbols-outlined icon-sm">edit</span>
              </button>
              <button
                @click="$emit('delete', resource)"
                class="btn btn-ghost btn-xs btn-square text-error hover:bg-error/10"
              >
                <span class="material-symbols-outlined icon-sm"> delete </span>
              </button>
            </div>
          </div>

          <!-- 价格和碳排放因子 -->
          <div class="flex items-center justify-between mt-3 pt-3 border-t border-base-content/10">
            <div class="flex items-center gap-1">
              <span class="material-symbols-outlined icon-sm text-fg-subtle"> payments </span>
              <span class="text-sm font-medium text-base-content">
                <span class="font-mono">¥</span>
                <span class="font-num">{{ fmtNumber(resource.unitPrice, 2) }}</span>
              </span>
              <span class="text-xs text-fg-subtle">/{{ resource.unit }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="material-symbols-outlined icon-sm text-fg-subtle">co2</span>
              <span class="text-sm text-base-content/70 font-num">
                {{ fmtNumber(resource.carbonFactor, 2) }}
              </span>
              <span class="text-xs text-fg-subtle">kg/{{ resource.unit }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
