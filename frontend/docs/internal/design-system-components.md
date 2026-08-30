# 设计系统组件文档

> 生成时间: 2026-03-08
> 分析范围: src/components/ 下的核心 UI 组件

---

## 组件总览

| 组件         | 路径                                       | 类别      | 复杂度 |
| ------------ | ------------------------------------------ | --------- | ------ |
| TaskCard     | `src/components/schedule/TaskCard.vue`     | 数据展示  | 高     |
| ResourceCard | `src/components/resource/ResourceCard.vue` | 数据展示  | 中     |
| ConfirmModal | `src/components/common/ConfirmModal.vue`   | 反馈/交互 | 中     |
| BottomNav    | `src/components/BottomNav.vue`             | 导航      | 低     |

---

## 1. TaskCard - 任务卡片

### 1.1 组件分类

- **类别**: Data Display / Card
- **用途**: 展示单个任务/工序的信息，包括进度、状态、前置依赖等
- **设计系统**: DaisyUI Card + Material Symbols 图标

### 1.2 Props 接口

```typescript
interface TaskCardProps {
  task: TaskResp // 任务数据对象
}

// TaskResp 类型定义 (来自后端 API)
interface TaskResp {
  id: number
  code: string // 任务代码
  name: string // 任务名称
  duration: number // 工期(天)
  completed: number // 完成度 (0-1)
  description?: string // 任务描述
  isCritical: boolean // 是否关键路径
  predecessors: Array<{
    id: number
    code: string
    type: string
  }>
}

// 内部派生类型
interface TaskStatus {
  status: 'pending' | 'in_progress' | 'completed'
  statusColor: 'neutral' | 'primary' | 'success'
  statusText: '待开始' | '进行中' | '已完成'
}
```

### 1.3 Emits 事件

| 事件名              | 参数                                      | 描述         |
| ------------------- | ----------------------------------------- | ------------ |
| `edit`              | `[task: TaskResp]`                        | 编辑任务     |
| `delete`            | `[task: TaskResp]`                        | 删除任务     |
| `addPredecessor`    | `[task: TaskResp]`                        | 添加前置工序 |
| `removePredecessor` | `[task: TaskResp, predecessorId: number]` | 移除前置工序 |

### 1.4 变体组合

#### 状态变体 (基于 completed)

| 完成度              | 状态        | 颜色主题       | 状态图标       |
| ------------------- | ----------- | -------------- | -------------- |
| `completed = 0`     | pending     | neutral (灰色) | status-neutral |
| `0 < completed < 1` | in_progress | primary (绿色) | status-primary |
| `completed >= 1`    | completed   | success (绿色) | status-success |

#### 关键路径变体

| isCritical | 样式变化                          |
| ---------- | --------------------------------- |
| `true`     | 任务名称显示警告色 `text-warning` |
| `false`    | 任务名称默认颜色                  |

#### 前置依赖变体

| predecessors 长度 | 显示效果                        |
| ----------------- | ------------------------------- |
| `0`               | 只显示"添加前置工序"按钮        |
| `> 0`             | 显示所有前置依赖标签 + 删除按钮 |

#### 描述变体

| 条件                 | 显示效果                             |
| -------------------- | ------------------------------------ |
| `description` 存在   | 显示描述文本，限制2行 `line-clamp-2` |
| `description` 不存在 | 不渲染该区块                         |

### 1.5 视觉结构

```
┌─────────────────────────────────────────┐
│ [CODE] 任务名称                    [✎][🗑] │ ← 头部: 代码徽章 + 操作按钮
├─────────────────────────────────────────┤
│ 📅 {duration}天  ⚠️ 关键路径(可选)        │ ← 元信息行
├─────────────────────────────────────────┤
│ 任务描述文本...(可选)                    │ ← 描述区域
├─────────────────────────────────────────┤
│ 🔗 FS-A001 [×] 🔗 SS-B002 [×]    [+前置] │ ← 前置依赖区
├─────────────────────────────────────────┤
│ ● 已完成    [████████░░] 80%           │ ← 进度条区
└─────────────────────────────────────────┘
```

### 1.6 使用模式

```vue
<TaskCard
  :task="taskItem"
  @edit="handleEdit"
  @delete="handleDelete"
  @addPredecessor="handleAddPredecessor"
  @removePredecessor="handleRemovePredecessor"
/>
```

---

## 2. ResourceCard - 资源卡片

### 2.1 组件分类

- **类别**: Data Display / Card
- **用途**: 展示单个资源（材料/设备/人工）的基本信息和价格
- **设计系统**: DaisyUI Card + Material Symbols 图标

### 2.2 Props 接口

```typescript
interface ResourceCardProps {
  resource: Resource
}

// Resource 类型定义
interface Resource {
  id: number
  name: string // 资源名称
  category: ResourceCategory // 资源分类
  unitPrice: number // 单价
  unit: string // 计量单位
  carbonFactor: number // 碳排放因子
}

// 资源分类枚举
enum ResourceCategory {
  MATERIAL = 'material', // 材料
  EQUIPMENT = 'equipment', // 设备
  LABOR = 'labor', // 人工
}

// 分类配置映射
categoryConfigMap = {
  material: { icon: 'inventory_2' },
  equipment: { icon: 'construction' },
  labor: { icon: 'engineering' },
}
```

### 2.3 Emits 事件

| 事件名   | 参数                   | 描述     |
| -------- | ---------------------- | -------- |
| `edit`   | `[resource: Resource]` | 编辑资源 |
| `delete` | `[resource: Resource]` | 删除资源 |

### 2.4 变体组合

#### 分类变体

| category    | 图标         | 颜色暗示 |
| ----------- | ------------ | -------- |
| `material`  | inventory_2  | 默认     |
| `equipment` | construction | 默认     |
| `labor`     | engineering  | 默认     |

### 2.5 视觉结构

```
┌─────────────────────────────────────────┐
│ ┌──┐                                    │
│ │📦│  资源名称                    [✎][🗑]│ ← 图标 + 名称 + 操作
│ └──┘  ID: 12345                        │
├─────────────────────────────────────────┤
│ 💴 ¥1,234 /吨      🌿 0.5 kg/吨        │ ← 价格和碳排放
└─────────────────────────────────────────┘
```

### 2.6 使用模式

```vue
<ResourceCard :resource="resourceItem" @edit="handleEdit" @delete="handleDelete" />
```

---

## 3. ConfirmModal - 确认弹窗

### 3.1 组件分类

- **类别**: Feedback / Modal
- **用途**: 需要用户确认操作的模态对话框
- **设计系统**: DaisyUI Modal + Teleport

### 3.2 Props 接口

```typescript
interface ConfirmModalProps {
  title?: string // 标题 (默认: '确认')
  message?: string // 消息内容 (默认: '')
  confirmText?: string // 确认按钮文本 (默认: '确认')
  cancelText?: string // 取消按钮文本 (默认: '取消')
  confirmType?: 'primary' | 'error' | 'warning' | 'neutral' // 确认按钮样式 (默认: 'primary')
  showCancel?: boolean // 是否显示取消按钮 (默认: true)
  closeOnClickOverlay?: boolean // 点击遮罩关闭 (默认: true)
  closeOnPressEscape?: boolean // 按ESC关闭 (默认: true)
}

// v-model 绑定
modelValue: boolean // 控制显示/隐藏
```

### 3.3 Emits 事件

| 事件名    | 参数 | 描述               |
| --------- | ---- | ------------------ |
| `confirm` | `[]` | 用户点击确认       |
| `cancel`  | `[]` | 用户点击取消或关闭 |

### 3.4 变体组合

#### 确认按钮类型变体

| confirmType | 按钮样式      | 适用场景      |
| ----------- | ------------- | ------------- |
| `primary`   | `btn-primary` | 普通确认      |
| `error`     | `btn-error`   | 删除/危险操作 |
| `warning`   | `btn-warning` | 警告性操作    |
| `neutral`   | `btn-neutral` | 中性操作      |

#### 显示模式变体

| showCancel | 效果                  |
| ---------- | --------------------- |
| `true`     | 显示取消 + 确认双按钮 |
| `false`    | 只显示确认按钮        |

#### 内容变体

| 条件             | 效果           |
| ---------------- | -------------- |
| `message` 存在   | 显示消息文本   |
| `message` 不存在 | 仅显示插槽内容 |
| 使用默认插槽     | 自定义复杂内容 |

### 3.5 视觉结构

```
┌─────────────────────────────────────────┐
│              (半透明遮罩)                │
│  ┌─────────────────────────────────┐    │
│  │ 标题                            │    │ ← 标题区
│  ├─────────────────────────────────┤    │
│  │ 消息内容或自定义内容             │    │ ← 内容区
│  ├─────────────────────────────────┤    │
│  │              [取消] [确认]       │    │ ← 操作区
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

### 3.6 使用模式

#### 基础用法

```vue
<ConfirmModal
  v-model="showModal"
  title="删除确认"
  message="确定要删除此项目吗？"
  confirm-type="error"
  confirm-text="删除"
  @confirm="handleDelete"
/>
```

#### 自定义内容

```vue
<ConfirmModal v-model="showModal" title="详细确认">
  <div class="custom-content">
    <!-- 自定义复杂内容 -->
  </div>
</ConfirmModal>
```

---

## 4. BottomNav - 底部导航

### 4.1 组件分类

- **类别**: Navigation / Tab Bar
- **用途**: 应用底部主导航
- **设计系统**: Fixed Position + DaisyUI 颜色系统

### 4.2 Props 接口

```typescript
// 无 Props - 内部硬编码配置

interface NavItem {
  path: string // 路由路径
  icon: string // Material Symbols 图标名
  label: string // 标签文本
}

// 内部导航配置
const navItems: NavItem[] = [
  { path: '/', icon: 'description', label: '日报' },
  { path: '/schedule', icon: 'calendar_today', label: '进度' },
  { path: '/insights', icon: 'monitoring', label: '分析' },
  { path: '/settings', icon: 'settings', label: '设置' },
]
```

### 4.3 Emits 事件

**无 Emits** - 使用 Vue Router 的 RouterLink 进行导航

### 4.4 变体组合

#### 状态变体 (基于当前路由)

| 条件                       | 样式                                |
| -------------------------- | ----------------------------------- |
| `route.path === item.path` | `text-primary` (主色)               |
| 其他                       | `text-base-content/70` (70% 透明度) |

### 4.5 视觉结构

```
┌─────────────────────────────────────────┐
│ 📄    📅    📊    ⚙️                    │ ← 图标行
│ 日报   进度   分析   设置                │ ← 标签行
└─────────────────────────────────────────┘
```

固定底部高度: `h-16` (64px)

### 4.6 使用模式

```vue
<!-- App.vue 中使用 -->
<template>
  <div class="app">
    <main>
      <RouterView />
    </main>
    <BottomNav />
  </div>
</template>
```

---

## 5. 组件依赖关系

```
┌─────────────────────────────────────────────────┐
│                   App.vue                       │
│  ┌─────────────────────────────────────────┐   │
│  │           RouterView                    │   │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐  │   │
│  │  │Daily    │ │Schedule │ │Insights  │  │   │
│  │  │Report   │ │View     │ │View      │  │   │
│  │  │View     │ │         │ │          │  │   │
│  │  └────┬────┘ └────┬────┘ └────┬─────┘  │   │
│  │       │           │           │         │   │
│  │       ▼           ▼           ▼         │   │
│  │  ┌─────────┐ ┌─────────┐               │   │
│  │  │TaskCard │ │Resource │               │   │
│  │  │         │ │Card     │               │   │
│  │  └─────────┘ └─────────┘               │   │
│  └─────────────────────────────────────────┘   │
│                      ▲                          │
│                      │                          │
│              ┌───────────────┐                  │
│              │  ConfirmModal │ (全局弹窗)        │
│              │   BottomNav   │ (全局导航)        │
│              └───────────────┘                  │
└─────────────────────────────────────────────────┘
```

---

## 6. 设计令牌映射

### 6.1 颜色系统 (DaisyUI)

| 令牌           | 值        | 用途                   |
| -------------- | --------- | ---------------------- |
| `primary`      | `#1fdb6d` | 主操作、进度、激活状态 |
| `success`      | -         | 完成状态               |
| `warning`      | -         | 关键路径标记           |
| `error`        | -         | 删除按钮、危险操作     |
| `neutral`      | -         | 待开始状态、次要信息   |
| `base-200`     | `#1a2d24` | 卡片背景               |
| `base-300`     | -         | 边框、分割线           |
| `base-content` | -         | 主要文本               |

### 6.2 间距系统

| 组件         | 间距模式                               |
| ------------ | -------------------------------------- |
| TaskCard     | `p-4` 内边距, `gap-2/3` 元素间距       |
| ResourceCard | `p-4` 内边距, `gap-3` 元素间距         |
| ConfirmModal | `py-2` 内容间距, `modal-action` 按钮区 |
| BottomNav    | `h-16` 固定高度, `py-2` 内边距         |

### 6.3 图标系统 (Material Symbols)

| 图标名           | 用途         |
| ---------------- | ------------ |
| `edit`           | 编辑操作     |
| `delete`         | 删除操作     |
| `calendar_today` | 工期、日期   |
| `warning`        | 关键路径标记 |
| `link`           | 前置依赖     |
| `add`            | 添加操作     |
| `payments`       | 价格         |
| `co2`            | 碳排放       |
| `inventory_2`    | 材料资源     |
| `construction`   | 设备资源     |
| `engineering`    | 人工资源     |
| `description`    | 日报导航     |
| `monitoring`     | 分析导航     |
| `settings`       | 设置导航     |

---

## 7. 推荐 Vize 变体配置

### 7.1 TaskCard.art.vue 推荐变体

```typescript
// 变体定义
const variants = [
  // 状态变体
  { name: 'pending', props: { task: { completed: 0, isCritical: false } } },
  { name: 'in-progress', props: { task: { completed: 0.5, isCritical: false } } },
  { name: 'completed', props: { task: { completed: 1, isCritical: false } } },
  // 关键路径变体
  { name: 'critical', props: { task: { completed: 0.5, isCritical: true } } },
  // 有前置依赖
  { name: 'with-predecessors', props: { task: { predecessors: [...] } } },
  // 有描述
  { name: 'with-description', props: { task: { description: '...' } } },
]
```

### 7.2 ResourceCard.art.vue 推荐变体

```typescript
const variants = [
  { name: 'material', props: { resource: { category: 'material' } } },
  { name: 'equipment', props: { resource: { category: 'equipment' } } },
  { name: 'labor', props: { resource: { category: 'labor' } } },
]
```

### 7.3 ConfirmModal.art.vue 推荐变体

```typescript
const variants = [
  { name: 'default', props: { confirmType: 'primary' } },
  { name: 'danger', props: { confirmType: 'error' } },
  { name: 'warning', props: { confirmType: 'warning' } },
  { name: 'neutral', props: { confirmType: 'neutral' } },
  { name: 'no-cancel', props: { showCancel: false } },
  { name: 'with-message', props: { message: '确认消息' } },
]
```

### 7.4 BottomNav.art.vue 推荐变体

```typescript
const variants = [
  { name: 'daily-report-active', props: {} }, // 首页激活
  { name: 'schedule-active', props: {} }, // 进度页激活
  { name: 'insights-active', props: {} }, // 分析页激活
  { name: 'settings-active', props: {} }, // 设置页激活
]
```

---

## 8. 组件复用建议

### 8.1 可提取的通用模式

1. **卡片操作按钮组** - TaskCard 和 ResourceCard 都有悬停显示的编辑/删除按钮
2. **状态徽章** - 可提取为 StatusBadge 组件
3. **进度指示器** - TaskCard 的进度条可提取为 ProgressBar 组件

### 8.2 命名规范

- 组件名: PascalCase (TaskCard, ConfirmModal)
- Props: camelCase (confirmType, showCancel)
- Emits: camelCase (addPredecessor, removePredecessor)
- 事件参数: 使用 tuple 类型定义 `[task: TaskResp]`

### 8.3 TypeScript 最佳实践

```typescript
// ✅ 推荐: 使用 interface 定义 Props
interface ConfirmModalProps {
  title?: string
}

// ✅ 推荐: 使用 withDefaults 设置默认值
const props = withDefaults(defineProps<ConfirmModalProps>(), {
  title: '确认',
})

// ✅ 推荐: 显式定义 emits 参数类型
defineEmits<{
  edit: [task: TaskResp]
  delete: [task: TaskResp]
}>()
```
