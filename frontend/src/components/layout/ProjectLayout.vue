<script setup lang="ts">
import { useProjectContext } from '@/composables/useProjectContext'
import BasicLayout from '@/components/layout/BasicLayout.vue'
</script>

<template>
  <BasicLayout>
    <RouterView />
  </BasicLayout>
</template>
