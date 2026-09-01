<script setup lang="ts">
/**
 * 资源使用量 - 统计
 *
 * 实际 vs 计划 分组条形图（按资源维度）。
 */
import { computed, onMounted, ref } from 'vue'
import { useQuery } from '@pinia/colada'
import ResourceUsageChart from '@/components/resource-usage/ResourceUsageChart.vue'
import ResourceUsageChartFilters from '@/components/resource-usage/ResourceUsageChartFilters.vue'
import { useProjectContext } from '@/composables/useProjectContext'
import { FETCH_ALL_PAGE_SIZE } from '@/constants/pagination'
import { listResourcesQuery } from '@/client/@pinia/colada.gen'
import type { ResourceResp } from '@/client/types.gen'

definePage({
  meta: {
    title: '统计',
    description: '实际 vs 计划使用量统计图表',
    icon: 'bar_chart',
    showInNav: true,
    parentName: '/project/[projectId]/resource-usage',
    navOrder: 3,
  },
})

const { currentProjectId } = useProjectContext()

const selectedResourceIds = ref<number[]>([])

// 拉取所有资源（按 category 列表做全集）
const { state: allResourcesState } = useQuery(() =>
  listResourcesQuery({
    path: { project_id: currentProjectId.value! },
    query: { per_page: FETCH_ALL_PAGE_SIZE },
  }),
)
const allResources = computed<ResourceResp[]>(() => allResourcesState.value?.data?.items ?? [])
const chartResources = computed<ResourceResp[]>(() =>
  allResources.value.filter((r) => selectedResourceIds.value.includes(r.id)),
)

// 初始化：默认选前 5 个资源
onMounted(() => {
  if (selectedResourceIds.value.length === 0 && allResources.value.length > 0) {
    selectedResourceIds.value = allResources.value.slice(0, 5).map((r) => r.id)
  }
})
</script>

<template>
  <ResourceUsageChartFilters v-model:selected-resource-ids="selectedResourceIds" />
  <ResourceUsageChart :resources="chartResources" />
</template>
