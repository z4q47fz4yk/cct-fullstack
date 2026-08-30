<script setup lang="ts">
defineEmits<{
  click: []
}>()
</script>

<template>
  <button
    class="btn btn-primary btn-circle fixed bottom-24 right-6 shadow-lg shadow-primary/20 z-40 w-14 h-14"
    @click="$emit('click')"
  >
    <span class="material-symbols-outlined icon-xl">add</span>
  </button>
</template>
