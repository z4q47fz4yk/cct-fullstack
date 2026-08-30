/**
 * 帕累托前沿图表配置 composable
 *
 * 提供四种视图模式的图表配置：
 * 1. 成本 vs 工期（2D）
 * 2. 成本 vs 碳排放（2D）
 * 3. 工期 vs 碳排放（2D）
 * 4. 成本 vs 工期 vs 碳排放（3D）
 *
 * 配色使用 themeColors 读取 CSS 变量，自动跟随主题。
 * 散点采用设计师配色：帕累托解 = indigo（深空蓝紫），选中 = cyan，
 * 普通可行解 = indigo 半透明，文字/坐标轴用 fg-muted。
 */
import { computed, ref, type Ref } from 'vue'
import type { OptimizeSolution } from '@/client/types.gen'
import { getThemeColors, hexToRgb, withOpacity } from '@/utils/themeColors'
import { fmtDays, fmtNumber, fmtWanYuan } from '@/utils/format'

// ECharts 类型
export interface EChartsOption {
  [key: string]: unknown
}

// 视图模式类型
export type ViewMode = 'cost-duration' | 'cost-emission' | 'duration-emission' | '3d'

// 坐标轴配置
interface AxisConfig {
  xLabel: string
  yLabel: string
  zLabel?: string
  xUnit: string
  yUnit: string
  zUnit?: string
}

// 视图模式对应的坐标轴配置
export const axisConfigs: Record<ViewMode, AxisConfig> = {
  'cost-duration': {
    xLabel: '成本',
    yLabel: '工期',
    xUnit: '万',
    yUnit: '天',
  },
  'cost-emission': {
    xLabel: '成本',
    yLabel: '碳排放',
    xUnit: '万',
    yUnit: 't',
  },
  'duration-emission': {
    xLabel: '工期',
    yLabel: '碳排放',
    xUnit: '天',
    yUnit: 't',
  },
  '3d': {
    xLabel: '成本',
    yLabel: '工期',
    zLabel: '碳排放',
    xUnit: '万',
    yUnit: '天',
    zUnit: 't',
  },
}

// 数据范围，用于动态调整坐标轴
export interface DataRange {
  costMin: number
  costMax: number
  durationMin: number
  durationMax: number
  emissionMin: number
  emissionMax: number
}

export function computeDataRange(solutions: OptimizeSolution[]): DataRange {
  let costMin = Infinity,
    costMax = -Infinity
  let durationMin = Infinity,
    durationMax = -Infinity
  let emissionMin = Infinity,
    emissionMax = -Infinity

  for (const sol of solutions) {
    if (sol.cost < costMin) costMin = sol.cost
    if (sol.cost > costMax) costMax = sol.cost
    if (sol.duration < durationMin) durationMin = sol.duration
    if (sol.duration > durationMax) durationMax = sol.duration
    if (sol.emission < emissionMin) emissionMin = sol.emission
    if (sol.emission > emissionMax) emissionMax = sol.emission
  }

  return { costMin, costMax, durationMin, durationMax, emissionMin, emissionMax }
}

/** 下限取 min 往下留 10% 区间空间，且不低于 0 */
export function axisMin(min: number, max: number): number {
  const padding = (max - min) * 0.1
  return Math.max(0, Math.floor(min - padding))
}

/** 上限取 max 往上留 10% 区间空间 */
export function axisMax(_min: number, max: number): number {
  return Math.ceil(max + (max - _min) * 0.1)
}

/**
 * 生成 2D 散点图配置
 */
function generate2DOption(
  solutions: OptimizeSolution[],
  selectedId: number | null,
  axisConfig: AxisConfig,
): EChartsOption {
  const C = getThemeColors()
  const range = computeDataRange(solutions)
  // 分离普通点和选中点（存储完整 solution 对象以避免浮点数比较问题）
  interface DataPoint {
    value: [number, number]
    id: number
    cost: number
    duration: number
    emission: number
  }

  const normalData: DataPoint[] = []
  const selectedData: DataPoint[] = []

  solutions.forEach((sol) => {
    let x: number
    let y: number

    if (axisConfig.xLabel === '成本') {
      x = sol.cost / 10000
    } else if (axisConfig.xLabel === '工期') {
      x = sol.duration
    } else {
      x = sol.emission / 1000
    }

    if (axisConfig.yLabel === '成本') {
      y = sol.cost / 10000
    } else if (axisConfig.yLabel === '工期') {
      y = sol.duration
    } else {
      y = sol.emission / 1000
    }

    const point: DataPoint = {
      value: [x, y],
      id: sol.id,
      cost: sol.cost,
      duration: sol.duration,
      emission: sol.emission,
    }

    if (sol.id === selectedId) {
      selectedData.push(point)
    } else {
      normalData.push(point)
    }
  })

  // 根据视图维度确定 x/y 的数据范围（数据已按轴单位换算：成本万、碳排 t）
  const xMin =
    axisConfig.xLabel === '成本'
      ? axisMin(range.costMin / 10000, range.costMax / 10000)
      : axisConfig.xLabel === '工期'
        ? axisMin(range.durationMin, range.durationMax)
        : axisMin(range.emissionMin / 1000, range.emissionMax / 1000)
  const xMax =
    axisConfig.xLabel === '成本'
      ? axisMax(range.costMin / 10000, range.costMax / 10000)
      : axisConfig.xLabel === '工期'
        ? axisMax(range.durationMin, range.durationMax)
        : axisMax(range.emissionMin / 1000, range.emissionMax / 1000)
  const yMin =
    axisConfig.yLabel === '成本'
      ? axisMin(range.costMin / 10000, range.costMax / 10000)
      : axisConfig.yLabel === '工期'
        ? axisMin(range.durationMin, range.durationMax)
        : axisMin(range.emissionMin / 1000, range.emissionMax / 1000)
  const yMax =
    axisConfig.yLabel === '成本'
      ? axisMax(range.costMin / 10000, range.costMax / 10000)
      : axisConfig.yLabel === '工期'
        ? axisMax(range.durationMin, range.durationMax)
        : axisMax(range.emissionMin / 1000, range.emissionMax / 1000)

  return {
    backgroundColor: 'transparent',
    grid: {
      left: 60,
      right: 30,
      top: 30,
      bottom: 50,
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.indigo, 0.3),
      borderWidth: 1,
      textStyle: {
        color: C.baseContent,
        fontSize: 12,
      },
      extraCssText: 'font-family: inherit;',
      formatter: (params: {
        data: { id: number; cost: number; duration: number; emission: number }
      }) => {
        const sol = params.data
        return `
          <div style="padding: 4px 0;">
            <div style="font-weight: 600; margin-bottom: 4px;">方案 #${sol.id}</div>
            <div>成本：<span style="color: ${C.blue}">${fmtWanYuan(sol.cost)}万</span></div>
            <div>工期：<span style="color: ${C.blue}">${fmtDays(sol.duration)}</span></div>
            <div>碳排：<span style="color: ${C.success}">${fmtNumber(sol.emission / 1000, 2)}t</span></div>
          </div>
        `
      },
    },
    xAxis: {
      type: 'value',
      min: xMin,
      max: xMax,
      name: `${axisConfig.xLabel}（${axisConfig.xUnit}）`,
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: {
        color: C.label,
        fontSize: 12,
      },
      axisLine: {
        lineStyle: { color: withOpacity(C.label, 0.25) },
      },
      axisTick: {
        lineStyle: { color: withOpacity(C.label, 0.25) },
      },
      axisLabel: {
        color: C.label,
        fontSize: 11,
      },
      splitLine: {
        lineStyle: { color: withOpacity(C.label, 0.08) },
      },
    },
    yAxis: {
      type: 'value',
      min: yMin,
      max: yMax,
      name: `${axisConfig.yLabel}（${axisConfig.yUnit}）`,
      nameLocation: 'middle',
      nameGap: 40,
      nameTextStyle: {
        color: C.label,
        fontSize: 12,
      },
      axisLine: {
        lineStyle: { color: withOpacity(C.label, 0.25) },
      },
      axisTick: {
        lineStyle: { color: withOpacity(C.label, 0.25) },
      },
      axisLabel: {
        color: C.label,
        fontSize: 11,
      },
      splitLine: {
        lineStyle: { color: withOpacity(C.label, 0.08) },
      },
    },
    series: [
      {
        name: '帕累托解',
        type: 'scatter',
        data: normalData.map((p) => ({
          value: p.value,
          id: p.id,
          cost: p.cost,
          duration: p.duration,
          emission: p.emission,
        })),
        symbolSize: 11,
        itemStyle: {
          // 设计师：indigo 半透明 + 主品牌色描边
          color: `rgba(${hexToRgb(C.indigo)}, 0.35)`,
          borderColor: C.indigo,
          borderWidth: 1,
          shadowBlur: 8,
          shadowColor: `rgba(${hexToRgb(C.indigo)}, 0.3)`,
        },
        emphasis: {
          itemStyle: {
            color: C.indigo,
            borderColor: '#fff',
            borderWidth: 2,
            shadowBlur: 14,
            shadowColor: `rgba(${hexToRgb(C.indigo)}, 0.6)`,
          },
          scale: 1.5,
        },
      },
      ...(selectedData.length > 0
        ? [
            {
              name: '选中方案',
              type: 'scatter' as const,
              data: selectedData.map((p) => ({
                value: p.value,
                id: p.id,
                cost: p.cost,
                duration: p.duration,
                emission: p.emission,
              })),
              symbolSize: 16,
              itemStyle: {
                color: C.cyan,
                borderColor: '#fff',
                borderWidth: 2,
                shadowBlur: 12,
                shadowColor: C.cyan,
              },
            },
          ]
        : []),
    ],
  }
}

/**
 * 生成 3D 散点图配置
 */
function generate3DOption(solutions: OptimizeSolution[], selectedId: number | null): EChartsOption {
  const C = getThemeColors()
  const range = computeDataRange(solutions)
  // 分离普通点和选中点（存储完整 solution 对象以避免浮点数比较问题）
  interface DataPoint3D {
    value: [number, number, number]
    id: number
    cost: number
    duration: number
    emission: number
  }

  const normalData: DataPoint3D[] = []
  const selectedData: DataPoint3D[] = []

  solutions.forEach((sol) => {
    const point: DataPoint3D = {
      value: [sol.cost / 10000, sol.duration, sol.emission / 1000],
      id: sol.id,
      cost: sol.cost,
      duration: sol.duration,
      emission: sol.emission,
    }
    if (sol.id === selectedId) {
      selectedData.push(point)
    } else {
      normalData.push(point)
    }
  })

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: withOpacity(C.surfaceDeep, 0.95),
      borderColor: withOpacity(C.indigo, 0.3),
      borderWidth: 1,
      textStyle: {
        color: C.baseContent,
        fontSize: 12,
      },
      extraCssText: 'font-family: inherit;',
      formatter: (params: { data: DataPoint3D }) => {
        const sol = params.data
        return `
          <div style="padding: 4px 0;">
            <div style="font-weight: 600; margin-bottom: 4px;">方案 #${sol.id}</div>
            <div>成本：<span style="color: ${C.blue}">${fmtWanYuan(sol.cost)}万</span></div>
            <div>工期：<span style="color: ${C.blue}">${fmtDays(sol.duration)}</span></div>
            <div>碳排：<span style="color: ${C.success}">${fmtNumber(sol.emission / 1000, 2)}t</span></div>
          </div>
        `
      },
    },
    xAxis3D: {
      type: 'value',
      min: axisMin(range.costMin / 10000, range.costMax / 10000),
      max: axisMax(range.costMin / 10000, range.costMax / 10000),
      name: '成本（万）',
      nameLocation: 'middle',
      nameGap: 25,
      nameTextStyle: {
        color: C.blue,
        fontSize: 12,
      },
      axisLine: {
        show: true,
        lineStyle: { color: withOpacity(C.blue, 0.5) },
      },
      axisLabel: {
        color: C.blue,
        fontSize: 11,
      },
      splitLine: {
        show: true,
        lineStyle: { color: withOpacity(C.blue, 0.12) },
      },
    },
    yAxis3D: {
      type: 'value',
      min: axisMin(range.durationMin, range.durationMax),
      max: axisMax(range.durationMin, range.durationMax),
      name: '工期（天）',
      nameLocation: 'middle',
      nameGap: 25,
      nameTextStyle: {
        color: C.blue,
        fontSize: 12,
      },
      axisLine: {
        show: true,
        lineStyle: { color: withOpacity(C.blue, 0.5) },
      },
      axisLabel: {
        color: C.blue,
        fontSize: 11,
      },
      splitLine: {
        show: true,
        lineStyle: { color: withOpacity(C.blue, 0.12) },
      },
    },
    zAxis3D: {
      type: 'value',
      min: axisMin(range.emissionMin / 1000, range.emissionMax / 1000),
      max: axisMax(range.emissionMin / 1000, range.emissionMax / 1000),
      name: '碳排放（t）',
      nameLocation: 'middle',
      nameGap: 25,
      nameTextStyle: {
        color: C.blue,
        fontSize: 12,
      },
      axisLine: {
        show: true,
        lineStyle: { color: withOpacity(C.blue, 0.5) },
      },
      axisLabel: {
        color: C.blue,
        fontSize: 11,
      },
      splitLine: {
        show: true,
        lineStyle: { color: withOpacity(C.blue, 0.12) },
      },
    },
    grid3D: {
      left: 60,
      right: 60,
      top: 30,
      bottom: 50,
      viewControl: {
        autoRotate: false,
        distance: 150,
        beta: 30,
        alpha: 30,
      },
      axisLabel: {
        color: C.blue,
        fontSize: 11,
      },
      splitLine: {
        show: true,
        lineStyle: { color: withOpacity(C.blue, 0.08) },
      },
    },
    series: [
      {
        name: '帕累托解',
        type: 'scatter3D',
        data: normalData,
        symbolSize: 10,
        itemStyle: {
          color: C.indigo,
          opacity: 0.85,
        },
        emphasis: {
          itemStyle: {
            color: '#fff',
            opacity: 1,
          },
        },
      },
      ...(selectedData.length > 0
        ? [
            {
              name: '选中方案',
              type: 'scatter3D' as const,
              data: selectedData,
              symbolSize: 16,
              itemStyle: {
                color: C.cyan,
                borderColor: '#fff',
                borderWidth: 2,
                shadowBlur: 15,
                shadowColor: C.cyan,
              },
            },
          ]
        : []),
    ],
  }
}

/**
 * useParetoChart composable
 */
export function useParetoChart(solutions: Ref<OptimizeSolution[]>, selectedId: Ref<number | null>) {
  const viewMode = ref<ViewMode>('cost-duration')

  /**
   * 根据当前视图模式生成图表配置
   */
  const chartOption = computed<EChartsOption>(() => {
    if (solutions.value.length === 0) {
      return {}
    }

    if (viewMode.value === '3d') {
      return generate3DOption(solutions.value, selectedId.value)
    }

    const axisConfig = axisConfigs[viewMode.value as ViewMode]
    return generate2DOption(solutions.value, selectedId.value, axisConfig)
  })

  /**
   * 判断是否为 3D 视图
   */
  const is3DView = computed(() => viewMode.value === '3d')

  /**
   * 切换视图模式
   */
  function setViewMode(mode: ViewMode) {
    viewMode.value = mode
  }

  return {
    viewMode,
    chartOption,
    is3DView,
    setViewMode,
  }
}
