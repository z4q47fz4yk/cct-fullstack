<script setup lang="ts">
definePage({
  meta: {
    title: '项目概览',
    icon: 'dashboard',
    showInNav: true,
    navOrder: 5,
  },
  redirect: {
    name: '/project/[projectId]/settings/',
  },
})
</script>

<template>
  <RouterView />
</template>
