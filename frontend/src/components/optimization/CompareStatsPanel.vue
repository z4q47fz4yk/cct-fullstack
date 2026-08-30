<script setup lang="ts">
/**
 * 对比统计面板
 *
 * 两个运行的解集规模（原始/幸存/被支配）与最优工期/成本/碳排对比，
 * 附运行2 − 运行1 的差值（三项目标均越低越好，负值 = 运行2 更优）。
 */
import { computed } from 'vue'
import { useParetoCompare } from '@/composables/useParetoCompare'
import ChartEmptyState from '@/components/common/ChartEmptyState.vue'
import { fmtDays, fmtNumber, fmtWanYuan } from '@/utils/format'
import { getThemeColors } from '@/utils/themeColors'

const compare = useParetoCompare()

function fmtBestDuration(v: number | null): string {
  return v !== null ? fmtDays(v) : '—'
}
function fmtBestCost(v: number | null): string {
  return v !== null ? `${fmtWanYuan(v)} 万` : '—'
}
function fmtBestEmission(v: number | null): string {
  return v !== null ? `${fmtNumber(v / 1000, 2)} t` : '—'
}

interface DeltaRow {
  key: string
  label: string
  left: string
  right: string
  delta: string | null
  deltaBetter: boolean | null
}

function buildRows() {
  const [a, b] = compare.statsByRun.value
  if (!a || !b) return [] as DeltaRow[]

  // 生成对比前未计算支配关系，幸存/被支配行不展示
  const rows: DeltaRow[] = [
    {
      key: 'total',
      label: '解集规模（原始）',
      left: String(a.total),
      right: String(b.total),
      delta: null,
      deltaBetter: null,
    },
    ...(compare.hasMerged.value
      ? [
          {
            key: 'survivor',
            label: '非支配（幸存）',
            left: String(a.survivor),
            right: String(b.survivor),
            delta: null,
            deltaBetter: null,
          },
          {
            key: 'dominated',
            label: '被支配/重复',
            left: String(a.dominated),
            right: String(b.dominated),
            delta: null,
            deltaBetter: null,
          },
        ]
      : []),
  ]

  const diff = (
    av: number | null,
    bv: number | null,
    fmt: (v: number) => string,
  ): { delta: string; better: boolean | null } => {
    if (av === null || bv === null) return { delta: '—', better: null }
    const d = bv - av
    const sign = d > 0 ? '+' : d < 0 ? '-' : '±'
    const better = d === 0 ? null : d < 0
    return { delta: `${sign}${fmt(Math.abs(d))}`, better }
  }

  const durationDiff = diff(a.bestDuration, b.bestDuration, (v) => fmtDays(v))
  const costDiff = diff(a.bestCost, b.bestCost, (v) => `${fmtWanYuan(v)} 万`)
  const emissionDiff = diff(a.bestEmission, b.bestEmission, (v) => `${fmtNumber(v / 1000, 2)} t`)

  rows.push(
    {
      key: 'duration',
      label: '最优工期',
      left: fmtBestDuration(a.bestDuration),
      right: fmtBestDuration(b.bestDuration),
      delta: durationDiff.delta,
      deltaBetter: durationDiff.better,
    },
    {
      key: 'cost',
      label: '最优成本',
      left: fmtBestCost(a.bestCost),
      right: fmtBestCost(b.bestCost),
      delta: costDiff.delta,
      deltaBetter: costDiff.better,
    },
    {
      key: 'emission',
      label: '最优碳排',
      left: fmtBestEmission(a.bestEmission),
      right: fmtBestEmission(b.bestEmission),
      delta: emissionDiff.delta,
      deltaBetter: emissionDiff.better,
    },
  )
  return rows
}

const rows = computed<DeltaRow[]>(() => buildRows())

const hasData = computed(() => compare.statsByRun.value.length === 2)

/** 每次调用读取主题色，跟随主题切换刷新 */
function colorOf(index: number) {
  const tc = getThemeColors()
  return index === 0 ? tc.indigo : tc.cyan
}
</script>

<template>
  <div>
    <h2 class="section-title">对比统计</h2>

    <ChartEmptyState
      v-if="!hasData"
      icon="query_stats"
      title="暂无对比数据"
      description="选择两个运行并生成对比后展示"
    />

    <table v-else class="w-full text-sm table-num">
      <thead>
        <tr class="border-b border-base-300/60">
          <th class="text-left font-normal text-fg-muted py-2 pr-2">指标</th>
          <th
            v-for="(s, idx) in compare.statsByRun.value"
            :key="s.runId"
            class="text-right font-medium py-2 px-2"
          >
            <span
              class="inline-block w-2 h-2 rounded-full mr-1 align-middle"
              :style="{ background: colorOf(idx) }"
            ></span>
            {{ s.label }}
          </th>
          <th class="text-right font-normal text-fg-muted py-2 pl-2">差值</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.key" class="border-b border-base-300/40">
          <td class="py-2 pr-2 text-fg-muted">{{ row.label }}</td>
          <td class="text-right py-2 px-2">{{ row.left }}</td>
          <td class="text-right py-2 px-2">{{ row.right }}</td>
          <td
            class="text-right py-2 pl-2 font-num"
            :class="
              row.deltaBetter === null
                ? 'text-fg-subtle'
                : row.deltaBetter
                  ? 'text-success'
                  : 'text-error'
            "
          >
            {{ row.delta ?? '—' }}
          </td>
        </tr>
      </tbody>
    </table>

    <p class="text-xs text-fg-subtle mt-3 leading-relaxed">
      差值为「右侧运行 − 左侧运行」，三项目标均越低越好：负值（绿色）表示右侧更优。
    </p>
  </div>
</template>
