<script setup lang="ts">
definePage({
  meta: {
    title: '碳排数据看板',
    description: '碳排数据看板',
    icon: 'description',
    showInNav: true,
    navOrder: 6,
  },
  redirect: {
    name: '/project/[projectId]/statistics',
  },
})
</script>

<template>
  <RouterView />
</template>
