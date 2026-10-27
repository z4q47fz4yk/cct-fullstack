<script setup lang="ts">
/**
 * 资源使用量 - 顶级容器
 *
 * 两个子页（侧边栏导航）：
 * - history    历史批次（默认）
 * - entry      录入（手动/日报统一入口）
 */
definePage({
  meta: {
    title: '活动数据管理',
    description: '计划/实际资源使用量录入与历史批次',
    icon: 'inventory_2',
    showInNav: true,
    navOrder: 3,
  },
  redirect: {
    name: '/project/[projectId]/resource-usage/entry-actual',
  },
})
</script>

<template>
  <RouterView />
</template>
