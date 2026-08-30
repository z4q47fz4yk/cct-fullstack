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
├── EmissionAnalysisTab.vue       # 碳排放分析
├── ResourceConstraintForm.vue    # 资源约束表单
├── ResourceConstraintList.vue    # 约束列表
├── ResourceReuseConfigForm.vue   # 复用配置表单
└── ResourceReuseConfigList.vue   # 复用配置列表
```

## WHERE TO LOOK

| 功能         | 组件                                          |
| ------------ | --------------------------------------------- |
| 配置优化参数 | `OptimizationConfig.vue`                      |
| 监控运行状态 | `RunStatusBar.vue`                            |
| 查看帕累托解 | `ParetoChart.vue` + `ParetoSolutionsList.vue` |
| 碳排放分析   | `EmissionAnalysisTab.vue`                     |
| 资源约束     | `ResourceConstraintForm/List.vue`             |
| 复用配置     | `ResourceReuseConfigForm/List.vue`            |

## CONVENTIONS

### 状态管理

- 使用 `useInsightsStore` (Pinia)
- 状态流转：IDLE → RUNNING → COMPLETED/FAILED
- 配置持久化：`useProjectStorage('insights:config', ...)`

### 图表

- 帕累托图：3D 散点 (echarts-gl)
- 颜色：`getThemeColors()` 读取 CSS 变量
- 空状态：`<ChartEmptyState>`
