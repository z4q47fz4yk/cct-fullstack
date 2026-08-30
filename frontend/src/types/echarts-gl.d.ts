/**
 * echarts-gl 类型声明
 */
declare module 'echarts-gl' {
  import type { Component } from 'echarts'

  export const Scatter3DChart: Component
  export const Bar3DChart: Component
  export const Line3DChart: Component
  export const SurfaceChart: Component
  export const Map3DChart: Component
  export const ScatterGL3DChart: Component
  export const GraphGL3DChart: Component
  export const Grid3DComponent: Component
  export const Geo3DComponent: Component
  export const Map3DComponent: Component
  export const Globe3DComponent: Component
  export const Model3DComponent: Component
  export const Axis3DComponent: Component
  export const OrbitControl: Component
  export const AreaPois3DChart: Component
  export const Rectiso3DChart: Component
  export const theme: Record<string, unknown>
}
