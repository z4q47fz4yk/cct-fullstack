<script setup lang="ts">
definePage({
  meta: {
    title: '分析洞察',
    description: 'NSGA-II 多目标优化',
    icon: 'insights',
    showInNav: true,
    navOrder: 4,
  },
  redirect: {
    name: '/project/[projectId]/insights/optimization',
  },
})
</script>

<template>
  <RouterView />
</template>
