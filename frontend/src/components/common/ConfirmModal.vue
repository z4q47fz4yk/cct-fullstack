<script setup lang="ts">
import { computed } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'

const {
  title = '确认',
  message = '',
  confirmText = '确认',
  cancelText = '取消',
  confirmType = 'primary',
  showCancel = true,
  closeOnClickOverlay = true,
  closeOnPressEscape = true,
} = defineProps<{
  title?: string
  message?: string
  confirmText?: string
  cancelText?: string
  confirmType?: 'primary' | 'error' | 'warning' | 'neutral'
  showCancel?: boolean
  closeOnClickOverlay?: boolean
  closeOnPressEscape?: boolean
}>()

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

// 确认按钮类名
const confirmButtonClass = computed(() => {
  const typeMap = {
    primary: 'btn-primary',
    error: 'btn-error',
    warning: 'btn-warning',
    neutral: 'btn-neutral',
  }
  return `btn ${typeMap[confirmType]}`
})

function handleConfirm() {
  emit('confirm')
  open.value = false
}

function handleCancel() {
  emit('cancel')
  open.value = false
}
</script>

<template>
  <BaseModal
    v-model:open="open"
    :title="title"
    :close-on-overlay="closeOnClickOverlay"
    :close-on-escape="closeOnPressEscape"
    class="max-w-sm"
    @close="handleCancel"
  >
    <p v-if="message" class="text-base-content/80 py-2">
      {{ message }}
    </p>

    <!-- 自定义内容插槽 -->
    <slot />

    <template #actions>
      <button v-if="showCancel" class="btn btn-ghost" @click="handleCancel">
        {{ cancelText }}
      </button>
      <button :class="confirmButtonClass" @click="handleConfirm">
        {{ confirmText }}
      </button>
    </template>
  </BaseModal>
</template>
