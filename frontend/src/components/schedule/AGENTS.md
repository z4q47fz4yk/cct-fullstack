# Schedule Components

## OVERVIEW

任务/进度管理相关组件，包含表格、表单、卡片、甘特图等 (8 files)。

## STRUCTURE

```
schedule/
├── TaskTable.vue          # 任务列表表格
├── TaskForm.vue           # 创建/编辑表单
├── TaskCard.vue           # 任务卡片
├── TaskFAB.vue            # 浮动操作按钮
├── GanttChart.vue         # 甘特图视图
├── AddPredecessorModal.vue # 添加前置依赖模态框
└── StatsOverview.vue      # 统计概览
```

## WHERE TO LOOK

| 功能           | 组件                                   |
| -------------- | -------------------------------------- |
| 任务 CRUD 表单 | `TaskForm.vue` — vee-validate + zod    |
| 任务列表展示   | `TaskTable.vue` — 带编辑/删除/前置依赖 |
| 前置依赖选择   | `AddPredecessorModal.vue`              |
| 关键路径展示   | `TaskCard.vue` — `isCritical` 高亮     |
| 甘特图渲染     | `GanttChart.vue` — CSS Grid            |
| API 调用封装   | `src/composables/useScheduleApi.ts`    |

## CONVENTIONS

### 表格模式

```typescript
const tableHeaders = [{ key: 'name', label: '名称', width: '30%' }]
```

### 表单模式

```vue
<TaskForm
  mode="create" | "edit"
  :initial-data="task"
  :is-submitting
  @submit="handleSubmit"
  @cancel="handleCancel"
/>
```

### 事件命名

- `@edit` — 编辑，payload 为实体
- `@delete` — 删除，payload 为实体
- `@add-predecessor` — 添加前置依赖

### Modal 模式

```vue
<dialog class="modal" :class="{ 'modal-open': showModal }">
```
