<script setup lang="ts">
interface Props {
  colspan?: number
  title?: string
  description?: string
  icon?: string
}

const {
  colspan = 1,
  title = '暂无数据',
  description = '暂无数据',
  icon = 'inbox',
} = defineProps<Props>()
</script>

<template>
  <tr>
    <td :colspan="colspan" class="text-center py-8">
      <div class="flex flex-col items-center gap-3">
        <div class="w-16 h-16 rounded-full bg-base-300 flex items-center justify-center">
          <span class="material-symbols-outlined icon-2xl text-base-content/30">{{ icon }}</span>
        </div>
        <div>
          <h3 class="text-lg font-semibold text-base-content/70">{{ title }}</h3>
          <p class="text-sm text-fg-subtle mt-1">{{ description }}</p>
        </div>
      </div>
    </td>
  </tr>
</template>
