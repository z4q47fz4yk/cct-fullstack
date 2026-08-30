<script setup lang="ts">
/**
 * ProjectOverviewCards - 项目碳排放统计卡片
 *
 * 3 张卡片：总碳排放 / 覆盖月份数 / 涉及资源数
 * 使用 StatCard 组件取代 createReusableTemplate 重复实现
 */
import StatCard from '@/components/common/StatCard.vue'
import { fmtNumber } from '@/utils/format'

const {
  totalEmissionKg,
  totalEmissionTon,
  totalMonths,
  totalResources,
  loading = false,
} = defineProps<{
  totalEmissionKg: number
  totalEmissionTon: number
  totalMonths: number
  totalResources: number
  loading?: boolean
}>()

const formattedEmission = () => {
  if (totalEmissionTon >= 0.01) return `${fmtNumber(totalEmissionTon, 2)} t`
  return `${fmtNumber(totalEmissionKg, 0)} kg`
}
</script>

<template>
  <!-- 3 张卡片 -->
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
    <StatCard label="总碳排放" :value="formattedEmission()" icon="eco" color="success" />
    <StatCard
      label="覆盖月份数"
      :value="totalMonths"
      unit="个月"
      icon="calendar_month"
      color="info"
    />
    <StatCard
      label="涉及资源数"
      :value="totalResources"
      unit="种"
      icon="category"
      color="warning"
    />
  </div>
</template>
