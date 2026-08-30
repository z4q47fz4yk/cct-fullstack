<script setup lang="ts">
// 施工阶段已合并为「施工进度」单页全景图（甘特 + 天气 + 碳排放），
// 本页为死代码暂留，待重构时移除。保留文件以便后续回收图表逻辑。
import EmissionAnalysisTab from '@/components/optimization/EmissionAnalysisTab.vue'

definePage({
  meta: {
    title: '碳排放与成本',
    icon: 'co2',
    showInNav: false,
    parentName: '/project/[projectId]/insights',
    group: '施工阶段',
    navOrder: 2,
  },
})
</script>

<template>
  <EmissionAnalysisTab />
</template>
