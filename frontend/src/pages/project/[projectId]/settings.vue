<script setup lang="ts">
definePage({
  meta: {
    title: '项目信息管理',
    icon: 'grid_view',
    showInNav: true,
    navOrder: 1,
  },
  redirect: {
    name: '/project/[projectId]/settings/',
  },
})
</script>

<template>
  <RouterView />
</template>
