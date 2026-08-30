<script setup lang="ts">
import OptimizationConfig from '@/components/optimization/OptimizationConfig.vue'
import { useInsightsStore } from '@/stores/insights'

definePage({
  meta: {
    title: '优化配置',
    description: 'NSGA2 算法的参数，根据项目具体情况取值',
    icon: 'tune',
    showInNav: true,
    parentName: '/project/[projectId]/settings',
    navOrder: 5,
  },
})

const store = useInsightsStore()
</script>

<template>
  <section class="p-4 panel" aria-labelledby="nsga2-title">
    <h2 id="nsga2-title" class="section-title">NSGA2 参数</h2>

    <OptimizationConfig :config="store.config" @update:config="store.updateConfig($event)" />
  </section>
</template>
