<script setup lang="ts">
/**
 * EmissionByCategoryChart - 按资源类别的碳排放饼图
 *
 * 玫瑰饼图（roseType: 'radius'），中心显示总碳排放
 * 颜色来自 categoryColors（共享常量）
 * 项目中首次使用 PieChart（从 echarts/charts 引入）
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GraphicComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ResourceCategory } from '@/client/types.gen'
import { categoryConfigMap } from '@/types/resource'
import { getThemeColors, getCategoryColor } from '@/utils/themeColors'
import { fmtNumber } from '@/utils/format'

use([PieChart, TooltipComponent, LegendComponent, CanvasRenderer, GraphicComponent])

interface CategoryEmission {
  category: ResourceCategory
  emissionKg: number
}

interface BucketEmission {
  bucket: string
  emissionKg: number
}

const {
  byCategory,
  byBucket,
  totalEmissionKg,
  loading = false,
} = defineProps<{
  byCategory: CategoryEmission[]
  /** 按水电桶 / 类别聚合（bucket 优先，含 water/electricity） */
  byBucket?: BucketEmission[]
  totalEmissionKg?: number
  loading?: boolean
}>()

function bucketLabel(bucket: string): string {
  if (bucket === 'water') return '水电'
  if (bucket === 'electricity') return '电'
  const cfg = categoryConfigMap[bucket as ResourceCategory]
  return cfg?.label ?? bucket
}

function bucketColor(bucket: string): string {
  if (bucket === 'water' || bucket === 'electricity') {
    return getThemeColors().cyan
  }
  return getCategoryColor(bucket as ResourceCategory)
}

const chartOption = computed(() => {
  const source = byBucket ?? byCategory
  const data = source.map((c) => {
    const bucket = 'bucket' in c ? c.bucket : c.category
    return {
      name: bucketLabel(bucket),
      value: Math.round(c.emissionKg * 100) / 100,
      itemStyle: { color: bucketColor(bucket) },
    }
  })
  const tc = getThemeColors()

  return {
    tooltip: {
      trigger: 'item' as const,
      confine: true,
      formatter: (params: unknown) => {
        const p = params as { name: string; value: number; percent: number }
        if (!p) return ''
        return `<b>${p.name}</b><br/>${fmtNumber(p.value, 1)} kg（${p.percent}%）`
      },
    },
    legend: {
      orient: 'vertical' as const,
      right: 20,
      top: 'center' as const,
      textStyle: { color: tc.label, fontSize: 12 },
      itemWidth: 12,
      itemHeight: 12,
    },
    graphic: [
      // 第一行：小标签 "总碳排放"，位于饼图中心上方
      {
        type: 'text' as const,
        left: '39%', // 与 series.center[0] 对齐
        top: '45%', // 与 series.center[1] 对齐
        style: {
          text: '总碳排放',
          fontSize: 11,
          fill: tc.label,
          textAlign: 'center',
          textVerticalAlign: 'bottom',
          y: -12,
        },
      },
      // 第二行：主数值 "X.XX t"，位于饼图中心下方
      {
        type: 'text' as const,
        left: '39%',
        top: '55%',
        style: {
          text: totalEmissionKg !== undefined ? `${fmtNumber(totalEmissionKg / 1000, 2)} t` : '0 t',
          fontSize: 16,
          fontWeight: 'bold',
          fill: tc.label,
          textAlign: 'center',
          textVerticalAlign: 'top',
          y: 12,
        },
      },
    ],
    series: [
      {
        name: '碳排放',
        type: 'pie' as const,
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        roseType: 'radius' as const,
        label: { show: false },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold' as const,
          },
        },
        data,
      },
    ],
  }
})
</script>

<template>
  <div class="panel">
    <div class="p-4">
      <h2 class="text-base font-semibold text-base-content mb-4">资源类别碳排放构成</h2>

      <div v-if="loading" class="flex justify-center items-center h-80">
        <span class="loading loading-spinner loading-lg text-primary"></span>
      </div>

      <div
        v-else-if="byCategory.length === 0"
        class="flex flex-col items-center justify-center h-80 text-center"
      >
        <div class="w-16 h-16 rounded-full bg-base-300 flex items-center justify-center mb-3">
          <span class="material-symbols-outlined icon-2xl text-base-content/30">pie_chart</span>
        </div>
        <p class="text-fg-subtle">暂无使用量数据</p>
        <p class="text-xs text-base-content/40 mt-1">录入资源使用量后可查看碳排放构成</p>
      </div>

      <div v-else class="h-80">
        <v-chart :option="chartOption" :autoresize="true" class="w-full h-full" />
      </div>
    </div>
  </div>
</template>
