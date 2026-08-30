# Types

## OVERVIEW

领域类型定义 (9 files)。优先使用 `src/client/types.gen.ts` 自动生成的类型，仅在需要时派生。

## WHERE TO LOOK

| 类型       | 文件              | 说明                  |
| ---------- | ----------------- | --------------------- |
| API 类型   | `api.d.ts`        | API 扩展类型          |
| 确认弹窗   | `confirm.ts`      | ConfirmOptions/Result |
| 约束配置   | `constraint.ts`   | 资源约束类型          |
| 资源       | `resource.ts`     | 资源领域类型          |
| 复用配置   | `reuseConfig.ts`  | 资源复用配置          |
| 路由       | `router.d.ts`     | 路由扩展类型          |
| 进度       | `schedule.ts`     | 任务/进度类型         |
| 选择器     | `select.ts`       | 选择组件通用类型      |
| ECharts GL | `echarts-gl.d.ts` | 3D 图表类型声明       |

## CONVENTIONS

### 类型来源优先级

1. `src/client/types.gen.ts` — 自动生成，勿手动修改
2. `src/types/` — 领域建模、UI 专用、业务规则
3. 组件内 `defineProps<{...}>()` — 简单场景

### 命名规范

- 接口：`PascalCase`，无 `I` 前缀
- 类型别名：`PascalCase`
- 枚举值：`UPPER_SNAKE_CASE` (后端约定)

## ANTI-PATTERNS

- **禁止** 重复定义已生成的类型 — 用 `src/client/types.gen.ts`
- **禁止** 修改 `src/client/` 下的类型 — 运行 `vpr generate-api` 重新生成
