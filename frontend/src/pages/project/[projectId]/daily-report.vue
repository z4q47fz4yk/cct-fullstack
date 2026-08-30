<script setup lang="ts">
definePage({
  meta: {
    title: '日报处理',
    description: '解析施工中的施工日报,简化导入流程',
    icon: 'description',
    showInNav: true,
    navOrder: 1,
  },
  redirect: {
    name: '/project/[projectId]/daily-report/import',
  },
})
</script>

<template>
  <RouterView />
</template>
