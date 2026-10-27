<script setup lang="ts">
/**
 * 碳排数据看板 - 顶级容器
 *
 * 单个子页（statistics/index.vue）：全屏深色大屏。
 */
definePage({
  meta: {
    title: '碳排数据看板',
    description: '项目碳排放全景数据大屏',
    icon: 'monitor',
    showInNav: true,
    navOrder: 6,
  },
  redirect: {
    name: '/project/[projectId]/statistics/',
  },
})
</script>

<template>
  <RouterView />
</template>
