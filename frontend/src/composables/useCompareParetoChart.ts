/**
 * 对比帕累托前沿图表配置 composable
 *
 * 两个运行（如串行 vs 并行）的原始解集叠加展示：
 * - 每个运行一个系列（indigo / cyan），幸存（非支配）解实色
 * - 被支配/重复解以所属运行色的低透明度标出
 * - 选中解以白色描边放大置顶
 * - 支持 2D（成本/工期/碳排两两组合）与 3D 视图
 */
import { computed, ref, type Ref } from 'vue'
import {
  axisConfigs,
  axisMax,
  axisMin,
  computeDataRange,
  type EChartsOption,
  type ViewMode,
} from '@/composables/useParetoChart'
import { getThemeColors, hexToRgb, withOpacity } from '@/utils/themeColors'
import { fmtDays, fmtNumber, fmtWanYuan } from '@/utils/format'
import type { CompareRunGroup } from '@/composables/useParetoCompare'

export type { ViewMode } from '@/composables/useParetoChart'

const DOMINATED_OPACITY = 0.12

interface CompareDataPoint {
  value: [number, number] | [number, number, number]
  id: number
  cost: number
  duration: number
  emission: number
  dominated: boolean
  source: string
}

function buildTooltip(C: ReturnType<typeof getThemeColors>) {
  return {
    trigger: 'item' as const,
    backgroundColor: withOpacity(C.surfaceDeep, 0.95),
    borderColor: withOpacity(C.indigo, 0.3),
    borderWidth: 1,
    textStyle: { color: C.baseContent, fontSize: 12 },
    extraCssText: 'font-family: inherit;',
    formatter: (params: { data: CompareDataPoint }) => {
      const d = params.data
      const dominated = d.dominated
        ? `<div style="color: ${C.warning}; margin-top:2px;">被支配 / 目标值重复</div>`
        : ''
      return `
        <div style="padding: 4px 0;">
          <div style="font-weight: 600; margin-bottom: 4px;">方案 #${d.id}</div>
          <div>来源：<span style="color: ${C.info}">${d.source}</span></div>
          <div>成本：<span style="color: ${C.blue}">${fmtWanYuan(d.cost)}万</span></div>
          <div>工期：<span style="color: ${C.blue}">${fmtDays(d.duration)}</span></div>
          <div>碳排：<span style="color: ${C.success}">${fmtNumber(d.emission / 1000, 2)}t</span></div>
          ${dominated}
        </div>
      `
    },
  }
}

/** 组内数据点：幸存解实色，被支配解低透明度 */
function groupPoints(
  group: CompareRunGroup,
  dominatedIds: Set<number>,
  C: ReturnType<typeof getThemeColors>,
  xKey: 'cost' | 'duration' | 'emission',
  yKey: 'cost' | 'duration' | 'emission',
): CompareDataPoint[] {
  return group.solutions.map((sol) => {
    const dominated = dominatedIds.has(sol.id)
    // 数据点按轴单位换算：成本万、碳排 t、工期天
    const xVal =
      xKey === 'cost' ? sol.cost / 10000 : xKey === 'emission' ? sol.emission / 1000 : sol.duration
    const yVal =
      yKey === 'cost' ? sol.cost / 10000 : yKey === 'emission' ? sol.emission / 1000 : sol.duration
    return {
      value: [xVal, yVal] as [number, number],
      id: sol.id,
      cost: sol.cost,
      duration: sol.duration,
      emission: sol.emission,
      dominated,
      source: group.label,
    }
  })
}

function generate2DOption(
  groups: CompareRunGroup[],
  dominatedIds: Set<number>,
  selectedId: number | null,
  viewMode: ViewMode,
): EChartsOption {
  const C = getThemeColors()
  const axis = axisConfigs[viewMode]
  const xKey = axis.xLabel === '成本' ? 'cost' : axis.xLabel === '工期' ? 'duration' : 'emission'
  const yKey = axis.yLabel === '成本' ? 'cost' : axis.yLabel === '工期' ? 'duration' : 'emission'

  const all = groups.flatMap((g) => g.solutions)
  const range = computeDataRange(all)
  // 坐标轴与数据点同口径换算：成本 /10000（万）、碳排 /1000（t）、工期不变
  const rangeOf = (key: 'cost' | 'duration' | 'emission', pick: 'min' | 'max') => {
    const v =
      key === 'cost' ? range.costMin : key === 'duration' ? range.durationMin : range.emissionMin
    const vMax =
      key === 'cost' ? range.costMax : key === 'duration' ? range.durationMax : range.emissionMax
    const base = pick === 'min' ? v : vMax
    if (key === 'emission') return base / 1000
    if (key === 'cost') return base / 10000
    return base
  }
  const xMin = axisMin(rangeOf(xKey, 'min'), rangeOf(xKey, 'max'))
  const xMax = axisMax(rangeOf(xKey, 'min'), rangeOf(xKey, 'max'))
  const yMin = axisMin(rangeOf(yKey, 'min'), rangeOf(yKey, 'max'))
  const yMax = axisMax(rangeOf(yKey, 'min'), rangeOf(yKey, 'max'))

  const colorOf = (key: 'indigo' | 'cyan') => (key === 'indigo' ? C.indigo : C.cyan)

  const selectedPoint = groups
    .flatMap((g) => groupPoints(g, dominatedIds, C, xKey, yKey))
    .filter((p) => p.id === selectedId)

  return {
    backgroundColor: 'transparent',
    grid: { left: 60, right: 30, top: 30, bottom: 50 },
    tooltip: buildTooltip(C),
    xAxis: {
      type: 'value',
      min: xMin,
      max: xMax,
      name: `${axis.xLabel}（${axis.xUnit}）`,
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: { color: C.label, fontSize: 12 },
      axisLine: { lineStyle: { color: withOpacity(C.label, 0.25) } },
      axisTick: { lineStyle: { color: withOpacity(C.label, 0.25) } },
      axisLabel: { color: C.label, fontSize: 11 },
      splitLine: { lineStyle: { color: withOpacity(C.label, 0.08) } },
    },
    yAxis: {
      type: 'value',
      min: yMin,
      max: yMax,
      name: `${axis.yLabel}（${axis.yUnit}）`,
      nameLocation: 'middle',
      nameGap: 40,
      nameTextStyle: { color: C.label, fontSize: 12 },
      axisLine: { lineStyle: { color: withOpacity(C.label, 0.25) } },
      axisTick: { lineStyle: { color: withOpacity(C.label, 0.25) } },
      axisLabel: { color: C.label, fontSize: 11 },
      splitLine: { lineStyle: { color: withOpacity(C.label, 0.08) } },
    },
    series: [
      ...groups.map((g) => {
        const color = colorOf(g.color)
        return {
          name: g.label,
          type: 'scatter' as const,
          data: groupPoints(g, dominatedIds, C, xKey, yKey),
          symbolSize: 11,
          itemStyle: {
            color: (params: { data: CompareDataPoint }) =>
              params.data.dominated
                ? `rgba(${hexToRgb(color)}, ${DOMINATED_OPACITY})`
                : `rgba(${hexToRgb(color)}, 0.65)`,
            borderColor: (params: { data: CompareDataPoint }) =>
              params.data.dominated ? 'transparent' : color,
            borderWidth: 1,
          },
          emphasis: {
            itemStyle: { color, borderColor: '#fff', borderWidth: 2 },
            scale: 1.5,
          },
        }
      }),
      ...(selectedPoint.length > 0
        ? [
            {
              name: '选中方案',
              type: 'scatter' as const,
              data: selectedPoint,
              symbolSize: 16,
              itemStyle: { color: C.baseContent, borderColor: '#fff', borderWidth: 2 },
            },
          ]
        : []),
    ],
  }
}

function generate3DOption(
  groups: CompareRunGroup[],
  dominatedIds: Set<number>,
  selectedId: number | null,
): EChartsOption {
  const C = getThemeColors()
  const all = groups.flatMap((g) => g.solutions)
  const range = computeDataRange(all)
  const colorOf = (key: 'indigo' | 'cyan') => (key === 'indigo' ? C.indigo : C.cyan)

  const points = groups.flatMap((g) => {
    const color = colorOf(g.color)
    return g.solutions.map((sol) => {
      const dominated = dominatedIds.has(sol.id)
      return {
        value: [sol.cost / 10000, sol.duration, sol.emission / 1000] as [number, number, number],
        id: sol.id,
        cost: sol.cost,
        duration: sol.duration,
        emission: sol.emission,
        dominated,
        source: g.label,
        itemStyle: {
          color: dominated ? `rgba(${hexToRgb(color)}, ${DOMINATED_OPACITY})` : color,
          opacity: dominated ? DOMINATED_OPACITY : 0.85,
        },
      }
    })
  })
  const selectedPoint = points.filter((p) => p.id === selectedId)

  return {
    backgroundColor: 'transparent',
    tooltip: buildTooltip(C),
    xAxis3D: {
      type: 'value',
      min: axisMin(range.costMin / 10000, range.costMax / 10000),
      max: axisMax(range.costMin / 10000, range.costMax / 10000),
      name: '成本（万）',
      nameLocation: 'middle',
      nameGap: 25,
      nameTextStyle: { color: C.blue, fontSize: 12 },
      axisLine: { show: true, lineStyle: { color: withOpacity(C.blue, 0.5) } },
      axisLabel: { color: C.blue, fontSize: 11 },
      splitLine: { show: true, lineStyle: { color: withOpacity(C.blue, 0.12) } },
    },
    yAxis3D: {
      type: 'value',
      min: axisMin(range.durationMin, range.durationMax),
      max: axisMax(range.durationMin, range.durationMax),
      name: '工期（天）',
      nameLocation: 'middle',
      nameGap: 25,
      nameTextStyle: { color: C.blue, fontSize: 12 },
      axisLine: { show: true, lineStyle: { color: withOpacity(C.blue, 0.5) } },
      axisLabel: { color: C.blue, fontSize: 11 },
      splitLine: { show: true, lineStyle: { color: withOpacity(C.blue, 0.12) } },
    },
    zAxis3D: {
      type: 'value',
      min: axisMin(range.emissionMin / 1000, range.emissionMax / 1000),
      max: axisMax(range.emissionMin / 1000, range.emissionMax / 1000),
      name: '碳排放（t）',
      nameLocation: 'middle',
      nameGap: 25,
      nameTextStyle: { color: C.blue, fontSize: 12 },
      axisLine: { show: true, lineStyle: { color: withOpacity(C.blue, 0.5) } },
      axisLabel: { color: C.blue, fontSize: 11 },
      splitLine: { show: true, lineStyle: { color: withOpacity(C.blue, 0.12) } },
    },
    grid3D: {
      left: 60,
      right: 60,
      top: 30,
      bottom: 50,
      viewControl: { autoRotate: false, distance: 150, beta: 30, alpha: 30 },
      axisLabel: { color: C.blue, fontSize: 11 },
      splitLine: { show: true, lineStyle: { color: withOpacity(C.blue, 0.08) } },
    },
    series: [
      {
        name: '对比解集',
        type: 'scatter3D',
        data: points,
        symbolSize: 10,
        emphasis: { itemStyle: { color: '#fff', opacity: 1 } },
      },
      ...(selectedPoint.length > 0
        ? [
            {
              name: '选中方案',
              type: 'scatter3D' as const,
              data: selectedPoint,
              symbolSize: 16,
              itemStyle: { color: C.baseContent, borderColor: '#fff', borderWidth: 2 },
            },
          ]
        : []),
    ],
  }
}

export function useCompareParetoChart(
  groups: Ref<CompareRunGroup[]>,
  dominatedIds: Ref<Set<number>>,
  selectedId: Ref<number | null>,
  hasMerged: Ref<boolean>,
) {
  const viewMode = ref<ViewMode>('cost-duration')

  /** 未生成对比时视为无被支配解（避免全部点被半透明化） */
  const effectiveDominated = computed(() =>
    hasMerged.value ? dominatedIds.value : new Set<number>(),
  )

  const chartOption = computed<EChartsOption>(() => {
    if (groups.value.length === 0) return {}
    if (viewMode.value === '3d') {
      return generate3DOption(groups.value, effectiveDominated.value, selectedId.value)
    }
    return generate2DOption(
      groups.value,
      effectiveDominated.value,
      selectedId.value,
      viewMode.value,
    )
  })

  const is3DView = computed(() => viewMode.value === '3d')

  function setViewMode(mode: ViewMode) {
    viewMode.value = mode
  }

  return { viewMode, chartOption, is3DView, setViewMode }
}
