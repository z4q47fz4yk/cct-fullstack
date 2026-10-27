<script setup lang="ts">
/**
 * 计划数据录入（设计稿菜单入口）
 *
 * 复用录入页并固定「计划」口径（界面入口拆分，录入逻辑完全一致）。
 */
import EntryView from './entry.vue'

definePage({
  meta: {
    title: '计划数据录入',
    description: '按施工工序录入计划资源使用量',
    icon: 'edit_calendar',
    showInNav: true,
    parentName: '/project/[projectId]/resource-usage',
    navOrder: 2,
  },
})
</script>

<template>
  <EntryView pinned-type="PLANNED" />
</template>
