# 施工多目标优化系统前端

**Generated:** 2026-07-25
**Commit:** 7a4760d
**Branch:** main

## OVERVIEW

Vue 3 前端应用，用于施工数据管理与 NSGA-II 多目标优化。获取施工日报数据，分配资源到工序，进行成本/工期/碳排放优化并可视化帕累托解集。

## STRUCTURE

```
src/
├── pages/              # 页面组件 (file-based routing)
│   └── project/[projectId]/
│       ├── daily-report/   # 日报处理向导 (5步)
│       ├── insights/       # 优化分析
│       └── settings/       # 项目设置
├── components/
│   ├── schedule/       # 任务管理组件
│   ├── resource/       # 资源管理组件
│   ├── optimization/   # 优化配置组件
│   ├── common/         # 通用组件 (16 files)
│   ├── ui/             # 基础 UI 组件 (BaseModal)
│   ├── daily-report/   # 日报处理组件
│   ├── resource-usage/ # 资源使用组件
│   └── layout/         # 布局组件
├── composables/        # API 封装 (21 files)
├── stores/             # Pinia 状态 (report.ts, insights.ts)
├── types/              # 领域类型定义
├── utils/              # 工具函数
└── client/             # 自动生成的 API 客户端 (勿手动修改)
```

## WHERE TO LOOK

| Task           | Location                                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| 添加新页面     | `src/pages/` — 创建 `.vue` 文件，路由自动生成                                                           |
| 添加新 API     | 后端更新 OpenAPI → 根 AGENTS.md 契约 checklist（`scripts/openapi-export.sh` + `scripts/gen-client.sh`） |
| 修改主题变量   | `src/assets/base.css` — 主题 CSS 变量 (starglass / starglass-light)                                     |
| 修改组件样式   | `src/assets/components.css` — 自研组件层 (类名与 DaisyUI 兼容)                                          |
| 面板容器       | `src/assets/panel.css` — panel / panel-hover / panel-grid 原子类                                        |
| 任务/进度逻辑  | `src/composables/useScheduleApi.ts`                                                                     |
| 日报工作流状态 | `src/stores/report.ts` (`useDailyReportStoreV2`)                                                        |
| 优化分析状态   | `src/stores/insights.ts` (`useInsightsStore`)                                                           |
| 优化参数配置   | `src/types/optimization.ts`                                                                             |
| 资源管理 API   | `src/composables/useResourceApi.ts`                                                                     |
| 图表颜色       | `src/utils/themeColors.ts` — 从 CSS 变量读取                                                            |
| 资源类别色     | `getCategoryColor()` — 类别色与语义色分离（材料=青，绿仅用于低碳）                                      |
| 错误处理       | `src/utils/error.ts` — ApiError + formatHttpError                                                       |
| 数字格式化     | `src/utils/format.ts` — fmtNumber, fmtWanYuan, fmtDays, fmtEmission 等                                  |

## CONVENTIONS

### 路由

- 文件路由：`src/pages/` 目录结构 → 路由自动生成 (vue-router/vite)
- 路由配置：`definePage({ meta: { title: '...' } })`
- 类型文件：`typed-router.d.ts` 在项目根目录 (非 src/)
- 项目路由：`/project/:projectId/*` — 所有项目页面在此下

### API 调用

- 使用 composables 封装，不直接调用 SDK
- `useQuery`/`useMutation` 来自 `@pinia/colada`
- Mutation 成功后调用 `queryCache.invalidateQueries()`
- 项目上下文：`useProjectContext()` 获取 `currentProjectId`

### API 客户端（@hey-api 生成物）

客户端由 `scripts/gen-client.sh`（`vpr generate-api`）从入库根 `openapi.json` 离线生成。

```typescript
import { useQuery } from '@pinia/colada'
import { listOptimizeRecordQuery } from '@/client/@pinia/colada.gen'

// 返回 reactive 对象，无需手动转换为 store
const { data, asyncStatus, refresh } = useQuery(() => ({
  ...listOptimizeRecordQuery({ path: { id: someValue } }),
  enabled: isActive.value,
  staleTime: 1000,
}))
```

- 优先使用生成的类型，避免重复定义；仅在涉及领域建模/用户体验/业务规则时才派生类型
- 后端返回 `Any` 或命名不规范时，反馈后端修复 OpenAPI，勿前端适配（见下方 ANTI-PATTERNS）

### 表单

- vee-validate + valibot 验证 (非 zod)
- 组件层语义类：`fieldset`, `fieldset-legend`, `input`
- **禁止** `form-control`, `label-text` (已废弃)

### 表单校验模式（vee-validate v4）

- 用 `defineField` 不用 `useField`（useField 与 useForm 上下文脱节）
- 模板必须 `v-bind="xxxAttrs"` 透传验证触发器
- `defineField` 值类型为 `T | undefined`，提交时用 `??` 提供默认值
- 参考实现：`src/components/resource/ResourceForm.vue`

### 已废弃类名（自动拦截）

`form-control` / `label-text` / `label-text-alt` 等 DaisyUI 兼容层遗留类名已被组件层废弃：
新代码混入会在 **pre-commit 钩子自动拦截**（`scripts/check-deprecated-classes.sh`，暂存 .vue 即检），
也可手动全量扫描 `bash scripts/check-deprecated-classes.sh`。废弃清单与替代方案以该脚本为唯一事实来源。

### 样式

- Tailwind CSS 4 + 自研组件层 (无 DaisyUI)
- 主题：`starglass` (深色) / `starglass-light` (浅色)，CSS 变量定义在 `base.css`
- 设计系统：**工程数据面板** — 平实底色、发丝线分割、紧凑控件、等宽数字（无玻璃模糊/渐变/光晕）
- **主色**：工程蓝 `--color-primary` (oklch 250°)；info 青蓝 (230°)
- **语义色专用**：
  - 绿 `success` = 低碳/减排；橙 `--color-accel` = 加速/压缩工期；红 `error` = 关键路径与超标
  - 琥珀 `warning` = 警告/需注意；蓝 `info` = 常规信息/进行中；靛 `indigo` = 帕累托解集
  - 紫 `violet` = 加速且低碳双策略；灰 `label` = 中性/普通模式
  - 类别色与语义色分离（`getCategoryColor()`）：人工=蓝、机械=琥珀、材料=青、运输=紫、其他=灰
- 字体：Inter + 思源黑体回退 (`--font-sans`)，等宽 JetBrains Mono；**数字一律用 `font-num`** (tabular-nums)
- 圆角 token：`--radius-box` 0.5rem / `--radius-field` 0.375rem / `--radius-pill` 9999px
- 阴影三阶：`--shadow-glass-1/2/3`（层级提示，不承担视觉分隔）；缓动：`--ease-soft` / `--ease-snap`
- 图标：Material Symbols (`material-symbols-outlined`)
- **无** `tailwind.config.js` — Tailwind v4 使用 CSS 配置

### Tailwind 动态类名陷阱

用字符串插值动态生成类名（如 `:class="\`text-${color}\`"`）在 Tailwind CSS 中无效——
Tailwind 静态扫描源码提取类名，无法识别运行时生成的字符串。用对象语法显式列出所有可能类名：

```vue
<!-- ❌ 错误 -->
<span :class="`text-${statusColor}`"></span>

<!-- ✅ 正确 -->
<span
  :class="{
    'text-success': statusColor === 'success',
    'text-primary': statusColor === 'primary',
    'text-neutral': statusColor === 'neutral',
  }"
></span>
```

### 破坏性操作流程（删除/重置/停止优化/导入提交）

所有不可逆或半不可逆操作按 3 步执行：

```ts
// 1. 二次确认（a11y 友好，自带 ESC / Enter / focus trap）
const ok = await confirmDanger('确定删除 X？')
if (!ok.confirmed) return

// 2. mutation 包 try/catch：失败 toast + 控制台日志
try {
  await mutation.mutateAsync(...)
} catch (e) {
  notifyError({ title: '操作失败', description: formatHttpError(e) })
  console.error('Failed:', e)
} finally {
  isSubmitting.value = false // 必须解除 loading，避免按钮卡死
}
```

- `confirmDanger` 提供 a11y，比 `alert()` 不会被浏览器屏蔽
- `notifyError` 走 vue-sonner，自动消失 + 多条堆叠
- `finally` 解除 loading 是 silent fail 的高发地——失败后按钮永远转圈最常见

### 数字格式化（全站统一）

| 数值          | 精度            | 函数          |
| ------------- | --------------- | ------------- |
| 成本（万元）  | 2 位小数+千分位 | `fmtWanYuan`  |
| 工期（天）    | 1 位小数        | `fmtDays`     |
| 碳排放 ≥1万kg | t，2 位小数     | `fmtEmission` |
| 碳排放 <1万kg | kg，整数千分位  | `fmtEmission` |
| 百分比        | 1 位小数        | `fmtPct`      |

- **禁止** 在业务代码直接 `.toFixed()` — 一律走 `src/utils/format.ts`
- 表格数字列：`<th>/<td>` 加 `table-num`（右对齐+等宽），表头配置 `num: true`
- 提示：`OptimizeSolution.emission` 与 `MonthlyResourceEmission.emission` 单位均为 **kgCO2e**；展示用 `fmtEmission()`（自动 t/kg）或 `fmtNumber(v / 1000, 2)` 转 t。

### 代码风格

- oxlint + oxfmt (非 ESLint/Prettier)
- 无分号，单引号，行宽 100

## ANTI-PATTERNS

- **禁止** 直接修改 `src/client/` — 运行 `scripts/gen-client.sh`（`vpr generate-api`，从入库根 `openapi.json` 离线生成）
- **禁止** 手动编辑 `typed-router.d.ts` — 自动生成
- **禁止** UI 使用英文 — 所有界面文本必须中文
  - 例外：专有名词（NSGA-II、Pareto/帕累托 等）；控制台日志中英文均可
- **禁止** 使用 `text-white` 等 Tailwind 原始类 — 用组件层语义类 (`btn`, `input` 等)
- **禁止** 玻璃/模糊/光晕效果 — 无 `backdrop-filter`、无渐变背景、无 glow 装饰；容器一律 `panel`
- **禁止** 业务代码 `.toFixed()` — 一律走 `src/utils/format.ts`（精度约定见上表）
- **禁止** 在页面添加 BottomNav — 由 App.vue 全局提供
- **禁止** Tailwind 动态类名插值 — 用对象语法
- **禁止** `alert()` / `confirm()` — 用 `useConfirm()`
- **禁止** mutation silent fail — 必须 `notifyError` + `console.error`
- 后端返回 `Any` 或命名不规范时 → 反馈后端修复 OpenAPI，勿前端适配

## COMMON COMPONENTS

写新页面前先扫一遍，避免重复造轮子：

| 场景             | 用什么                                       |
| ---------------- | -------------------------------------------- |
| KPI 数字卡片     | `<StatCard>`                                 |
| 图表空/加载状态  | `<ChartEmptyState>`                          |
| 长列表骨架       | `<LoadingState variant="skeleton">`          |
| 单条方案         | `<SchemeCard>`                               |
| 图标按钮         | `<IconAction>`                               |
| 错误占位         | `<ErrorState>`                               |
| 模态框           | `<BaseModal>` (原生 dialog 派，v-model:open) |
| 危险操作确认     | `useConfirm().confirmDanger`                 |
| Toast 通知       | `useToast().notifySuccess/Error/Warning`     |
| 图表主题色       | `getThemeColors()`                           |
| 资源类别色       | `getCategoryColor()`                         |
| 面板容器         | `panel` / `panel-hover` / `panel-grid`       |
| 项目范围状态隔离 | `useProjectStorage`                          |

## COMMANDS

项目由 `vp` 管理（vite 封装），**禁止** 使用 npm/pnpm 命令：

```bash
vp dev           # 启动开发服务器
vp build         # 构建生产版本（含类型检查）
vpr build-only   # 仅构建，不进行类型检查
vpr type-check   # 类型检查（vp check 不检查类型：oxlint 不支持 vue 模板）
vp check --fix   # 代码检查 + 格式化 (oxlint + oxfmt)
vp preview       # 预览生产构建
vpr generate-api # 从入库根 openapi.json 离线生成客户端（无后端运行亦可；推荐 scripts/gen-client.sh）
```

## NOTES

- Node.js 要求：`^20.19.0 || >=22.12.0`
- 后端 API：同源 `/api`（dev 由 vite 反代到本 worktree 后端，部署由 nginx 反代；见根 AGENTS.md）；跨机直连可改根 `.env` 的 `VITE_API_BASE`
- 无测试框架：项目暂无 Vitest/Jest（`vitest` 仅作为依赖存在）
- 无 CI/CD：无 GitHub Actions 配置
- Store 文件名 `report.ts`，导出 `useDailyReportStoreV2`
- Store 文件名 `insights.ts`，导出 `useInsightsStore`
