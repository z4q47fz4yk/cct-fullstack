# Optimization Components

## OVERVIEW

NSGA-II 多目标优化相关组件：配置、运行、结果展示、碳排放分析。

## STRUCTURE

```
optimization/
├── OptimizationConfig.vue        # 优化参数配置表单
├── RunStatusBar.vue              # 运行状态/进度条
├── ParetoChart.vue               # 帕累托解集散点图
├── ParetoSolutionsList.vue       # 解集列表
└── EmissionAnalysisTab.vue       # 碳排放分析
```

> 资源约束 / 周转复用配置已并入资源管理（`components/resource/ResourceForm.vue`，
> 通过 `useConstraintApi` / `useReuseConfigApi` 编排增删改）。

## WHERE TO LOOK

| 功能         | 组件                                          |
| ------------ | --------------------------------------------- |
| 配置优化参数 | `OptimizationConfig.vue`                      |
| 监控运行状态 | `RunStatusBar.vue`                            |
| 查看帕累托解 | `ParetoChart.vue` + `ParetoSolutionsList.vue` |
| 碳排放分析   | `EmissionAnalysisTab.vue`                     |

## CONVENTIONS

### 状态管理

- 使用 `useInsightsStore` (Pinia)
- 状态流转：IDLE → RUNNING → COMPLETED/FAILED
- 配置持久化：`useProjectStorage('insights:config', ...)`

### 图表

- 帕累托图：3D 散点 (echarts-gl)
- 颜色：`getThemeColors()` 读取 CSS 变量
- 空状态：`<ChartEmptyState>`
