<script setup lang="ts">
definePage({
  meta: {
    title: '日报处理',
    description: '解析施工中的施工日报,简化导入流程',
    icon: 'description',
    // 从侧边栏隐藏：日报导入是「资源使用量」模块的子流程，
    // 统一从资源使用量页「从日报导入」进入
    showInNav: false,
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
