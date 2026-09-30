<script setup lang="ts">
/**
 * ResourceSearch - Search input component for resources
 * 资源搜索组件
 */

const query = defineModel<string>('query')

const { placeholder = '搜索资源名称或ID...', disabled = false } = defineProps<{
  placeholder?: string
  disabled?: boolean
}>()
</script>

<template>
  <fieldset class="fieldset w-full">
    <label class="input w-full flex items-center gap-2">
      <span class="material-symbols-outlined text-neutral-content text-base"> search </span>
      <input
        v-model="query"
        type="text"
        :placeholder="placeholder"
        class="grow bg-transparent focus:outline-none"
        :disabled="disabled"
      />
    </label>
  </fieldset>
</template>
