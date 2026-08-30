<script setup lang="ts">
import type { ScheduleStats } from '@/client/types.gen'
import StatCard from '@/components/common/StatCard.vue'

const { stats, criticalPathCount = 0 } = defineProps<{
  stats: ScheduleStats
  criticalPathCount?: number
}>()
</script>

<template>
  <div class="grid grid-cols-3 gap-4">
    <StatCard label="总工序数" :value="stats.totalTasks" icon="checklist" color="primary" />
    <StatCard
      label="关键路径工期"
      :value="stats.criticalDuration"
      unit="天"
      icon="calendar_today"
      color="info"
    />
    <StatCard label="关键路径" :value="criticalPathCount" unit="个" icon="warning" color="error" />
  </div>
</template>
