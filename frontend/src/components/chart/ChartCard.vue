<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import type { ChartResp } from '@/client/types.gen'
import { useChartPieData } from '@/composables/useChartApi'
import { useTagPieChart, type PieSliceDatum } from '@/composables/useTagPieChart'
import { getSliceColor } from '@/utils/themeColors'
import { formatPct, formatTons, orderSlicesByChart, sliceValueByName } from '@/utils/chartSlices'
import { categoryConfigMap } from '@/types/resource'

/** 切片归属实体文案 */
const SLICE_ENTITY_LABEL: Record<string, string> = {
  RESOURCE: '资源',
  TASK: '任务',
  USAGE: '用量',
  ANY: '任一',
}

/**
 * 图表定义卡片（S3）
 *
 * 自带饼图数据查询：左侧迷你甜甜圈 + 右侧切片 chips（编号按 sortOrder）。
 */
const props = defineProps<{
  chart: ChartResp
}>()

const emit = defineEmits<{
  (e: 'edit', chart: ChartResp): void
  (e: 'delete', chart: ChartResp): void
}>()

const chartId = ref<number | null>(props.chart.id)
watch(
  () => props.chart.id,
  (id) => {
    chartId.value = id
  },
)

const { slices, totalEmission, isLoading } = useChartPieData(chartId)

// 按 sortOrder 排序后的切片（用于甜甜圈）
const orderedSlices = computed(() => orderSlicesByChart(slices.value))

const donutData = computed<PieSliceDatum[]>(() =>
  orderedSlices.value.map((s, i) => ({ name: s.name, value: s.value, color: getSliceColor(i) })),
)

const { chartOption } = useTagPieChart({
  slices: donutData,
  showLegend: false,
  centerTotal: computed(() => formatTons(totalEmission.value)),
})

// 绑定的全部标签（含零值），按 sortOrder 顺序展示 chips
const boundTags = computed(() =>
  [...(props.chart.tags ?? [])].sort((a, b) => a.sortOrder - b.sortOrder),
)

const totalKg = computed(() => totalEmission.value)
</script>

<template>
  <div class="panel p-4 flex flex-col gap-4">
    <!-- 头部 -->
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h3 class="text-[15px] font-semibold text-base-content truncate">{{ chart.name }}</h3>
        <p v-if="chart.description" class="text-[11px] text-fg-subtle mt-0.5 truncate">
          {{ chart.description }}
        </p>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <span
          class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-violet-500/10 text-violet-400 border border-violet-500/30 whitespace-nowrap"
          :title="`切片归属实体：${SLICE_ENTITY_LABEL[chart.sliceEntity] ?? chart.sliceEntity}`"
        >
          {{ SLICE_ENTITY_LABEL[chart.sliceEntity] ?? chart.sliceEntity }}
        </span>
        <button
          class="btn btn-ghost btn-xs btn-square shrink-0"
          title="编辑图表"
          @click="emit('edit', chart)"
        >
          <span class="material-symbols-outlined icon-sm text-fg-subtle">edit</span>
        </button>
      </div>
    </div>

    <!-- 资源分类过滤（RESOURCE 实体） -->
    <div
      v-if="
        chart.sliceEntity === 'RESOURCE' &&
        chart.resourceCategories &&
        chart.resourceCategories.length > 0
      "
      class="flex items-center gap-1.5 flex-wrap"
    >
      <span class="text-[10px] text-fg-subtle">分类过滤：</span>
      <span
        v-for="cat in chart.resourceCategories"
        :key="cat"
        class="text-[10px] px-1.5 py-0.5 rounded-full bg-base-200/60 border border-base-content/20 text-fg-muted"
      >
        {{ categoryConfigMap[cat]?.label ?? cat }}
      </span>
    </div>

    <!-- 主体：迷你甜甜圈 + 切片 chips -->
    <div class="flex items-start gap-4">
      <div class="w-36 h-36 shrink-0">
        <div v-if="isLoading" class="w-full h-full flex items-center justify-center">
          <span class="loading loading-spinner loading-md text-primary" />
        </div>
        <v-chart v-else :option="chartOption" :autoresize="true" class="w-full h-full" />
      </div>

      <div class="flex-1 min-w-0 flex flex-col gap-1.5">
        <div
          v-for="(tag, index) in boundTags"
          :key="tag.tagId"
          class="flex items-center gap-2 h-8 px-3 rounded-full bg-base-200/60 border border-base-content/20"
        >
          <span
            class="w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10px] font-mono shrink-0"
            :style="{ backgroundColor: `${getSliceColor(index)}22`, color: getSliceColor(index) }"
          >
            {{ index + 1 }}
          </span>
          <span
            class="w-2 h-2 rounded-full shrink-0"
            :style="{ backgroundColor: getSliceColor(index) }"
          />
          <span class="text-xs text-base-content truncate flex-1 min-w-0">{{ tag.tagName }}</span>
          <span class="text-[11px] font-mono text-fg-muted shrink-0">
            {{ formatPct(sliceValueByName(slices, tag.tagName), totalKg) }}
          </span>
        </div>
      </div>
    </div>

    <!-- 底部 -->
    <div class="flex items-center justify-between gap-3 pt-3 border-t border-base-content/20">
      <span class="text-[11px] text-fg-subtle"
        >绑定 {{ boundTags.length }} 个切片 · 按展示顺序排序</span
      >
      <div class="flex items-center gap-2">
        <button class="btn btn-ghost btn-xs" @click="emit('edit', chart)">
          <span class="material-symbols-outlined icon-sm">edit</span>
          编辑
        </button>
        <button class="btn btn-ghost btn-xs text-error" @click="emit('delete', chart)">
          <span class="material-symbols-outlined icon-sm">delete</span>
          删除
        </button>
      </div>
    </div>
  </div>
</template>
