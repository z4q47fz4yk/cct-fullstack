# Resource Components

## OVERVIEW

资源管理相关组件，包含分类标签、表格、表单、卡片等 (7 files)。

## STRUCTURE

```
resource/
├── ResourceTable.vue        # 资源列表表格
├── ResourceForm.vue         # 创建/编辑表单 (Modal)
├── ResourceCard.vue         # 资源卡片
├── ResourceList.vue         # 资源列表容器
├── ResourceSearch.vue       # 搜索输入
├── ResourceStats.vue        # 分类统计
└── ResourceCategoryTabs.vue # 分类标签切换
```

## WHERE TO LOOK

| 功能           | 组件                                |
| -------------- | ----------------------------------- |
| 资源 CRUD 表单 | `ResourceForm.vue` — Modal 表单     |
| 资源列表展示   | `ResourceTable.vue` — 带编辑/删除   |
| 分类切换       | `ResourceCategoryTabs.vue`          |
| 分类统计       | `ResourceStats.vue`                 |
| API 调用封装   | `src/composables/useResourceApi.ts` |

## CONVENTIONS

### 资源分类

```typescript
type ResourceCategory = 'labor' | 'machinery' | 'material' | 'transport' | 'others'
```

默认单位：

- `labor` → 工日
- `machinery` → 台班
- `material` → t
- `transport` → (km·t)⁻¹

### 表格模式

```typescript
const tableHeaders = [
  { key: 'name', label: '资源名称', width: 'flex-1' },
  { key: 'unitPrice', label: '单价', width: 'w-32' },
  { key: 'carbonFactor', label: '碳排放因子', width: 'w-32' },
]
```

### 表单模式

```vue
<ResourceForm
  v-model:show="showModal"
  v-model:resource="formData"
  :title="'新建资源'"
  :is-submitting
  @submit="handleSubmit"
  @cancel="handleCancel"
/>
```

### 事件命名

- `@edit` — 编辑，payload 为 Resource
- `@delete` — 删除，payload 为 Resource
