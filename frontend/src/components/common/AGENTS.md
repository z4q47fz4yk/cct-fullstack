# Common Components

## OVERVIEW

跨模块共享的通用 UI 组件 (16 files)。写新页面前先扫一遍，避免重复造轮子。

## WHERE TO LOOK

| 场景            | 组件                                             |
| --------------- | ------------------------------------------------ |
| KPI 数字卡片    | `StatCard.vue`                                   |
| 图表空/加载状态 | `ChartEmptyState.vue`                            |
| 长列表骨架      | `LoadingState.vue` (variant="skeleton")          |
| 单条方案        | `SchemeCard.vue`                                 |
| 图标按钮        | `IconAction.vue` (min 32px 触控)                 |
| 错误占位        | `ErrorState.vue` (支持 #actions slot)            |
| 表格空状态      | `TableEmptyState.vue`                            |
| 分页            | `PaginationBar.vue`                              |
| 确认弹窗        | `ConfirmModal.vue`                               |
| 搜索选择        | `SearchableSelect.vue`                           |
| 分段控制        | `SegmentControl.vue`                             |
| 主题切换        | `ThemeToggle.vue`                                |
| 甘特图          | `GanttChart.vue`                                 |
| 图表组件        | `EmissionTrendChart.vue`, `TopEmittersChart.vue` |

## CONVENTIONS

### 组件模式

- 所有组件使用 `<script setup lang="ts">`
- Props 使用 TypeScript 类型定义
- 事件使用 `defineEmits`
- 插槽使用 `defineSlots` 或 template 中 `#slotName`

### 样式

- 使用自研组件层语义类：`btn`, `input`, `fieldset` 等 (定义在 `src/assets/components.css`)
- 面板容器用原子类：`panel` (+ `panel-hover`/`panel-grid`) (定义在 `src/assets/panel.css`)
- 数字一律 `font-num` + 走 `src/utils/format.ts` 格式化
- **禁止** `text-white` 等 Tailwind 原始类
- **禁止** `backdrop-filter` / 渐变背景 / glow 装饰
- 颜色使用 CSS 变量：`var(--color-primary)`, `var(--color-base-content)` 等

### 图表

- 使用 `vue-echarts` + `echarts`
- 颜色从 `getThemeColors()` 读取，禁止硬编码 hex
- 空状态使用 `<ChartEmptyState>`

## ANTI-PATTERNS

- **禁止** 重复造轮子 — 先检查此目录
- **禁止** 硬编码颜色 — 用 `getThemeColors()`
- **禁止** 直接用 `alert()` / `confirm()` — 用 `useConfirm()`
