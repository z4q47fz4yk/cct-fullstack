<script setup lang="ts">
/**
 * 资源使用量 - 顶级容器
 *
 * 三个子页（侧边栏导航）：
 * - history    历史批次（默认）
 * - entry      录入（手动/日报统一入口）
 * - statistics 统计图表
 */
definePage({
  meta: {
    title: '资源使用量',
    description: '录入、查看与统计资源使用量（手动/日报统一入口）',
    icon: 'inventory_2',
    showInNav: true,
    navOrder: 3,
  },
  redirect: {
    name: '/project/[projectId]/resource-usage/history',
  },
})
</script>

<template>
  <RouterView />
</template>
