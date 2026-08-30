# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 软件总纲

该软件能够有某种方式获取施工中的数据（包括工序信息、工序的资源使用情况），从而为施工策略提供一些参考。所谓的施工策略，是用户定义的一系列施工模式，定义了从标准策略转变为该模式时，工序成本、工期、碳排放三者之间的关系。当工序的施工模式发生变化时，整个项目的成本、工期、碳排放会发生变化，可能变化数为各工序的可能模式的乘积。用户要求使用
nsga2 算法进行多目标的优化，并在前端进行帕累托解集的可视化。

本项目为该软件的前端部分。

# 开发命令

使用 vp 运行以下命令：

```bash
# 启动开发服务器
vp dev

# 构建生产版本（含类型检查）
vp build

# 仅构建，不进行类型检查
vpr build-only

# 类型检查(由于 vp 底层 oxlint 还不支持 vue 模板，vp check 不会进行类型检查)
vpr type-check

# 运行代码检查并格式化
vp check --fix

# 预览生产构建
vp preview

# 从后端 OpenAPI 规范生成 API 客户端
vpr generate-api
```

# 项目架构

## 技术栈

- **框架**: Vue 3.5 + Composition API (`<script setup>`)
- **语言**: TypeScript 5.9
- **构建工具**: Vite 8.0
- **路由**: Vue Router 5.0 (文件路由自动生成)
- **状态管理**: Pinia 3.0 + @pinia/colada
- **样式**: Tailwind CSS 4 + 自研玻璃组件层 (无 DaisyUI)
- **图标**: Material Symbols

## 目录结构

```
src/
├── assets/          # 全局样式 (base.css 主题变量 + components.css 组件层 + glass.css 原子类)
├── client/         # 自动生成的 API 客户端 (勿手动修改)
├── components/     # 可复用组件
│   ├── common/     # 通用组件 (ConfirmModal, Pagination, ErrorState)
│   ├── daily-report/ # 日报处理组件
│   ├── layout/     # 布局组件 (BottomNav, SideBar, BasicLayout)
│   ├── optimization/ # 优化配置组件
│   ├── resource/   # 资源管理组件
│   └── schedule/   # 进度管理组件
├── composables/    # API 封装逻辑 (useScheduleApi, useResourceApi)
├── pages/          # 页面组件 (文件路由，自动生成路由)
├── router/         # 路由配置 (自动导入)
├── stores/         # Pinia 状态管理
├── types/          # TypeScript 类型定义
├── App.vue        # 根组件
└── main.ts        # 应用入口
```

## 路由配置

使用文件路由 (vue-router/auto-routes)，`src/pages/` 目录结构自动生成路由。

| 路径                     | 页面文件                          | 说明         |
| ------------------------ | --------------------------------- | ------------ |
| `/`                      | `pages/index.vue`                 | 首页/默认页  |
| `/daily-report`          | `pages/daily-report.vue`          | 日报处理向导 |
| `/daily-report/import`   | `pages/daily-report/import.vue`   | 导入日报     |
| `/daily-report/allocate` | `pages/daily-report/allocate.vue` | 分配资源     |
| `/daily-report/review`   | `pages/daily-report/review.vue`   | 审核确认     |
| `/daily-report/confirm`  | `pages/daily-report/confirm.vue`  | 确认提交     |
| `/daily-report/success`  | `pages/daily-report/success.vue`  | 提交成功     |
| `/schedule`              | `pages/schedule.vue`              | 进度管理     |
| `/insights`              | `pages/insights.vue`              | 分析洞察     |
| `/settings`              | `pages/settings.vue`              | 设置         |

路由元信息在页面组件中使用 `definePage({ meta: { title: '...' } })` 定义。

### 侧边栏导航配置

在页面中添加 `showInNav` 和 `icon` 即可显示在侧边栏：

```typescript
definePage({
  meta: {
    title: '页面标题',
    icon: 'material_symbols图标名',
    showInNav: true,
    navOrder: 1, // 数字越小越靠前
    children: [
      // 可选：子菜单
      { path: '/xxx/yyy', title: '子页面' },
    ],
  },
})
```

侧边栏组件 `SideBar.vue` 会自动从路由配置中提取导航项。

## UI 设计系统

自研极光柔光玻璃设计系统 Starglass Aurora（无 DaisyUI），主题变量定义在 `src/assets/base.css`：

- **主题**: `starglass` (深色) / `starglass-light` (浅色)，CSS 变量切换 (`data-theme`)
- **极光三色**: 青 (200°) / 紫 (290°) / 粉 (340°)，背景为三色径向光斑 + `aurora-drift` 慢漂移
- **组件层**: `src/assets/components.css` — `btn`/`input`/`fieldset`/`modal`/`table` 等语义类 (类名与 DaisyUI 兼容，中性半透明底，无硬编码渐变)
- **玻璃容器**: `src/assets/glass.css` — 原子类 `glass-surface` (+ `glass-lift`/`glass-inset`/`glass-float`/`glass-aurora`/`glass-noise`/`glass-glow{色}`)
- **模态框**: `<BaseModal>` (原生 `<dialog>` 派，`src/components/ui/BaseModal.vue`)
- **字体**: Inter + 思源黑体；数字 `font-num` (tabular-nums)
- **设计稿**: `designs/starglass-aurora/*.png` — 组件双模式对照

核心布局模式：

- 底部导航栏 (BottomNav) - 由 App.vue 提供，各页面无需重复添加
- 页面布局使用 `h-full flex flex-col`，头部固定 `shrink-0`，内容区 `flex-1 overflow-y-auto`
- App.vue 主内容区使用 `overflow-hidden`，滚动由各页面自行处理

## 核心架构模式

### 布局架构

- **App.vue**: 提供 BottomNav 底部导航，包裹 RouterView 作为主内容区
- **各页面**: 独立处理滚动，使用 `flex-1 overflow-y-auto` 实现内容滚动
- **组件复用**: 通用组件放在 `components/common/`，业务组件按模块分目录

### 状态管理

- **Pinia**: 用于全局状态
  - Store 文件在 `src/stores/report.ts`
  - 主要导出: `useDailyReportStoreV2`
- **@pinia/colada**: 用于服务端状态（API 数据获取），简化异步状态管理
- 简单场景可直接用 colada，无需定义 Pinia store

### API 调用模式

- 使用 composables 封装 API 逻辑（如 `useScheduleApi.ts`、`useResourceApi.ts`）
- composables 内部调用 `useQuery` 或直接使用生成的 SDK
- Mutation 成功后调用 `queryCache.invalidateQueries()` 刷新缓存

## 关键配置文件

| 文件                   | 用途                                 |
| ---------------------- | ------------------------------------ |
| `vite.config.ts`       | Vite + Vue + Tailwind 配置           |
| `src/assets/base.css`  | Tailwind 导入 + 主题变量 (starglass) |
| `openapi-ts.config.ts` | API 客户端生成配置                   |
| `src/hey-api.ts`       | API 运行时配置 (Base URL)            |
| `typed-router.d.ts`    | 路由类型定义 (项目根目录)            |

## 代码风格

- 风格: 无分号，单引号，行宽限制 100 字符
- 配置文件: `vite.config.ts`

## 反模式 (禁止)

- **禁止** 修改 `src/client/` 目录 — 运行 `pnpm generate-api` 重新生成
- **禁止** 手动编辑 `typed-router.d.ts` — 自动生成
- **禁止** UI 使用英文 — 所有界面文本必须中文
- **禁止** 使用 `text-white` 等 Tailwind 原始类 — 用组件层语义类 (`btn`, `input` 等)
- **禁止** 在页面添加 BottomNav — 由 App.vue 全局提供
- **禁止** 在 Tailwind 类名中使用字符串插值 — 必须使用对象语法
- **禁止** `alert()` / `confirm()` — 用 `useConfirm().confirmDanger / confirmWarn` 弹出 `<ConfirmModal>`（a11y 与可控性）
- **禁止** mutation silent fail — 失败必须 `notifyError` + `console.error`，`finally` 中解除 loading

## 通用组件速查

写新页面或新组件前先扫一遍这里，避免重复造轮子：

| 场景                                        | 用什么                                       |
| ------------------------------------------- | -------------------------------------------- |
| KPI 数字卡片（label + value + unit + icon） | `<StatCard>`                                 |
| 图表的空 / 加载状态                         | `<ChartEmptyState>`                          |
| 长列表的骨架 / loading                      | `<LoadingState variant="skeleton">`          |
| 单条方案（label + 3 指标 + TOP 1 徽章）     | `<SchemeCard>`                               |
| 图标按钮（最小 32px 触控目标）              | `<IconAction>`                               |
| 错误占位卡片                                | `<ErrorState>`（支持 `#actions` slot）       |
| 危险操作二次确认（删除 / 重置 / 停止）      | `useConfirm().confirmDanger / confirmWarn`   |
| 普通 toast（成功 / 失败 / 警告）            | `useToast().notifySuccess / Error / Warning` |
| 图表中读取主题色                            | `getThemeColors()`（不要硬编码 hex）         |
| 项目范围 composable 状态隔离                | `useProjectStorage`（自动按 projectId 后缀） |

参考实现：`src/components/resource/ResourceForm.vue`。

## API 客户端架构

本项目使用 **@hey-api/openapi-ts** 从后端 OpenAPI 规范自动生成类型安全的 API 客户端：

### 生成流程

```bash
vpr generate-api  # 从 openapi.json 生成客户端代码
```

### 生成的代码

- `src/client/types.gen.ts` - 后端类型定义
- `src/client/sdk.gen.ts` - API 方法封装
- `src/client/@pinia/colada.gen.ts` - pinia colada 的 query 生成
- `src/client/index.ts` - 客户端导出
- `src/client/valibot.gen.ts` - valibot schema，用于表单校验

### 使用方式

使用 **@pinia/colada** 进行数据获取，它为 Pinia 提供响应式查询功能：

使用前请详细阅读 [hey-api 文档](https://heyapi.dev/docs/openapi/typescript/plugins/pinia-colada#queries) 以及 [pinia colada 文档](https://pinia-colada.esm.dev/guide/queries.html) 等相关页面，确保彻底理解 hey-api 生成的结构在 pinia colada 中的作用。使用 `markitdown` 命令获取文档，比如 `markitdown https://pinia-colada.esm.dev/guide/queries.html` 。

```typescript
import { useQuery } from '@pinia/colada'
import { listOptimizeRecordQuery } from '@/client/@pinia/colada.gen'

// 返回 reactive 对象，无需手动转换为 store
const { data, asyncStatus, refresh } = useQuery(() => {
  ...getOptimizeRecordStatusQuery({
    path: {id: somevalue},
    // ...
  }),
  enabled: isActive.value,
  staleTime: 1000,
})
```

### 架构原则

- 优先使用生成的类型，避免重复定义
- 仅在涉及领域建模、用户体验、业务规则时才派生类型
- 后端返回 Any 或命名不规范时，反馈给后端修复 OpenAPI 文档，而非前端适配

# 开发规则

## Tailwind CSS 动态类名陷阱

**问题**: 使用字符串插值动态生成类名（如 `:class="`text-${color}`"`）在 Tailwind CSS 中无效。

**原因**: Tailwind 通过静态扫描源代码提取类名，无法识别运行时动态生成的字符串。

**正确做法**: 使用对象语法显式列出所有可能的类名：

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

**适用范围**: 所有动态变化的类名（text-_, bg-_, border-_, status-_ 等）都需要遵循此规则。

## 界面语言规范

**所有用户界面文本必须使用中文**，即使 Stitch 设计稿或参考设计使用英文。

- ✅ **正确**: 标题、按钮、标签、提示文本使用中文
- ❌ **错误**: 直接复制设计稿中的英文文本到界面

**例外情况**:

- 专有名词: NSGA-II、Pareto（帕累托）等
- 控制台日志: 中英文均可

# 表单输入最佳实践

**必须使用自研组件层语义化样式**（定义在 `src/assets/components.css`，类名与 DaisyUI 兼容）。不允许使用 `text-red` 等非语义样式（使用 `text-error`）。表单结构：`fieldset` + `fieldset-legend` + `input`/`select`/`textarea`。参考 `src/components/resource/ResourceForm.vue`。

## 已废弃的类名（避免使用）

| 废弃类名         | 替代方案                               |
| ---------------- | -------------------------------------- |
| `form-control`   | 使用 `fieldset`                        |
| `label-text`     | 使用 `fieldset-legend` 或纯文本 `span` |
| `label-text-alt` | 使用 `label.label` 或描述性段落        |

# 表单校验模式

vee-validate v4 + valibot，文档用 `markitdown` 获取：

- 入门: `markitdown https://vee-validate.logaretm.com/v4/guide/composition-api/getting-started/`
- API: `markitdown https://vee-validate.logaretm.com/v4/api/use-form`

关键规则：

- 用 `defineField` 不用 `useField`（useField 与 useForm 上下文脱节）
- 模板必须 `v-bind="xxxAttrs"` 透传验证触发器
- `defineField` 值类型为 `T | undefined`，提交时用 `??` 提供默认值

参考: `src/components/resource/ResourceForm.vue`

# 破坏性操作流程

所有"删除 / 重置 / 停止优化 / 导入提交"等不可逆或半不可逆操作，必须按以下 3 步执行：

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
  isSubmitting.value = false  // 必须解除 loading，避免按钮卡死
}
```

为什么：

- `confirmDanger` 提供 a11y，比 `alert()` 不会被浏览器屏蔽
- `notifyError` 走 vue-sonner，自动消失 + 多条堆叠
- `finally` 解除 loading 是 silent fail 的高发地——失败后按钮永远转圈最常见

# 可用工具

- agent-browser: 加载 skill，通过 bash 命令 `agent-browser` 使用，如 `agent-browser open http://localhost:5173`
