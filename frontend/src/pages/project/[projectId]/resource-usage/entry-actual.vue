<script setup lang="ts">
/**
 * 实际数据录入（设计稿菜单入口）
 *
 * 复用录入页并固定「实际」口径（界面入口拆分，录入逻辑完全一致）。
 */
import EntryView from './entry.vue'

definePage({
  meta: {
    title: '实际数据录入',
    description: '按施工工序录入实际资源使用量',
    icon: 'edit_note',
    showInNav: true,
    parentName: '/project/[projectId]/resource-usage',
    navOrder: 3,
  },
})
</script>

<template>
  <EntryView pinned-type="ACTUAL" />
</template>
