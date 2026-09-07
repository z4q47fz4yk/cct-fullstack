<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useChartApi } from '@/composables/useChartApi'
import { useProjectContext } from '@/composables/useProjectContext'
import TagPieChartCard from '@/components/chart/TagPieChartCard.vue'
import LoadingState from '@/components/common/LoadingState.vue'
import { fmtNumber } from '@/utils/format'

/**
 * 标签碳排放占比区块（S5）
 *
 * 渲染项目下全部图表定义对应的饼图（2 列网格）；
 * 底部汇总条展示图表数 / 碳排放合计 / 隐藏零值切片数。
 */
const { charts, isLoading } = useChartApi()
const { currentProjectId } = useProjectContext()

const summaries = reactive<Record<number, { totalKg: number; hiddenCount: number }>>({})

function onSummary(payload: { chartId: number; totalKg: number; hiddenCount: number }) {
  summaries[payload.chartId] = { totalKg: payload.totalKg, hiddenCount: payload.hiddenCount }
}

// 图表增删后清理失效的汇总
watch(
  () => charts.value.map((c) => c.id).join(','),
  (ids) => {
    const valid = new Set(ids ? ids.split(',') : [])
    for (const key of Object.keys(summaries)) {
      if (!valid.has(key)) delete summaries[Number(key)]
    }
  },
)

const totalEmission = computed(() =>
  Object.values(summaries).reduce((sum, s) => sum + s.totalKg, 0),
)

const totalHidden = computed(() =>
  Object.values(summaries).reduce((sum, s) => sum + s.hiddenCount, 0),
)
</script>

<template>
  <section aria-labelledby="tag-charts-title" class="space-y-4">
    <!-- 区块头 -->
    <div class="flex items-center gap-3">
      <div class="min-w-0 flex-1">
        <h2 id="tag-charts-title" class="text-base font-semibold text-base-content">
          标签碳排放占比
        </h2>
        <p class="text-[11px] text-fg-subtle mt-0.5">
          切片为图表配置的标签组合，值为命中该切片（标签组且/或规则）的用量碳排放合计
        </p>
      </div>
      <span
        class="text-[11px] font-mono px-2 py-1 rounded-full bg-primary/12 text-primary shrink-0"
      >
        {{ charts.length }} 个图表
      </span>
    </div>

    <!-- 无图表引导 -->
    <div v-if="!isLoading && charts.length === 0" class="panel py-8 text-center">
      <div
        class="w-12 h-12 rounded-full bg-base-300/60 flex items-center justify-center mx-auto mb-3"
      >
        <span class="material-symbols-outlined icon-xl text-fg-subtle">donut_small</span>
      </div>
      <p class="text-sm text-fg-muted">尚未配置标签图表</p>
      <p class="text-xs text-fg-subtle mt-1">
        前往
        <RouterLink :to="`/project/${currentProjectId}/settings/charts`" class="link link-primary">
          设置 → 碳排放图表
        </RouterLink>
        配置切片创建饼图
      </p>
    </div>

    <template v-else>
      <div v-if="isLoading" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <LoadingState variant="skeleton" class="h-56" />
        <LoadingState variant="skeleton" class="h-56" />
      </div>

      <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <TagPieChartCard
          v-for="chart in charts"
          :key="chart.id"
          :chart="chart"
          @summary="onSummary"
        />
      </div>

      <!-- 汇总条 -->
      <div v-if="charts.length > 0" class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div class="panel px-4 py-3 flex items-center gap-3">
          <span class="material-symbols-outlined text-primary icon-md shrink-0">pie_chart</span>
          <div class="flex-1 min-w-0">
            <p class="text-[11px] text-fg-subtle">图表</p>
            <p class="font-mono text-sm font-semibold text-base-content">{{ charts.length }} 个</p>
          </div>
        </div>
        <div class="panel px-4 py-3 flex items-center gap-3">
          <span class="material-symbols-outlined text-success icon-md shrink-0">eco</span>
          <div class="flex-1 min-w-0">
            <p class="text-[11px] text-fg-subtle">碳排放合计</p>
            <p class="font-mono text-sm font-semibold text-base-content">
              {{ fmtNumber(totalEmission / 1000, 2) }} tCO₂e
            </p>
          </div>
        </div>
        <div class="panel px-4 py-3 flex items-center gap-3">
          <span class="material-symbols-outlined text-fg-subtle icon-md shrink-0"
            >visibility_off</span
          >
          <div class="flex-1 min-w-0">
            <p class="text-[11px] text-fg-subtle">隐藏零值切片</p>
            <p class="font-mono text-sm font-semibold text-base-content">{{ totalHidden }} 个</p>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
