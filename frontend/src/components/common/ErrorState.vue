<script setup lang="ts">
interface Props {
  title?: string
  description?: string
  retryText?: string
  icon?: string
}

const {
  title = '加载失败',
  description = '无法获取数据，请检查网络连接',
  retryText = '重试',
  icon = 'error_outline',
} = defineProps<Props>()

const emit = defineEmits<{
  retry: []
}>()
</script>

<template>
  <!--
    FIXME(architecture): 是否改用 notifyError({title, description, action}) 替代？
    推荐保留 ErrorState card——与 LoadingState/EmptyState 形成一致的「空/错/载」三态。
    详见 plans/ui-ux-promax-ui-ux-review-sleepy-pond.md 附录 B PR-T3。
  -->
  <div class="panel border border-error/20">
    <div class="items-center text-center py-8">
      <div class="w-16 h-16 rounded-full bg-error/10 flex items-center justify-center mb-4">
        <span class="material-symbols-outlined icon-2xl text-error">{{ icon }}</span>
      </div>
      <h3 class="text-lg font-semibold text-base-content/70">{{ title }}</h3>
      <p class="text-sm text-fg-subtle mt-1">{{ description }}</p>
      <div class="flex gap-2 mt-4">
        <slot name="actions">
          <button class="btn btn-primary btn-sm" @click="emit('retry')">{{ retryText }}</button>
        </slot>
      </div>
    </div>
  </div>
</template>
