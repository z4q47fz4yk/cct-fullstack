# Composables

## OVERVIEW

API 封装与共享逻辑 (21 files)。所有 API 调用通过 composables 封装，不直接使用 SDK。

## WHERE TO LOOK

| 功能             | 文件                      |
| ---------------- | ------------------------- |
| 任务/进度 API    | `useScheduleApi.ts`       |
| 资源管理 API     | `useResourceApi.ts`       |
| 项目 API         | `useProjectApi.ts`        |
| 资源用量 API     | `useResourceUsageApi.ts`  |
| 约束配置 API     | `useConstraintApi.ts`     |
| 复用配置 API     | `useReuseConfigApi.ts`    |
| 公共资源 API     | `usePublicResourceApi.ts` |
| 项目上下文       | `useProjectContext.ts`    |
| 项目存储隔离     | `useProjectStorage.ts`    |
| 确认弹窗         | `useConfirm.ts`           |
| Toast 通知       | `useToast.ts`             |
| 主题切换         | `useTheme.ts`             |
| 侧边栏导航       | `useSidebarNav.ts`        |
| 图表 composables | `useParetoChart.ts` 等    |

## CONVENTIONS

### API 封装模式

```typescript
export function useXxxApi(options: UseXxxApiOptions) {
  const queryCache = useQueryCache()
  const { currentProjectId } = useProjectContext()

  // 查询
  const { state, asyncStatus, error, refresh } = useQuery(() =>
    listXxxQuery({ path: { project_id: currentProjectId.value! } })
  )

  // Mutation
  const { mutateAsync: createXxx } = useMutation({
    ...createXxxMutation(),
    onSuccess: async () => {
      await queryCache.invalidateQueries({ key: listXxxQueryKey(...) })
    },
  })

  return { data, isLoading, createXxx, ... }
}
```

### 项目上下文

- `useProjectContext()` — 从路由提取 `projectId`，提供 `currentProjectId` 和 `isInProject`
- 所有项目范围的 API 调用必须使用 `currentProjectId.value!`

### 项目存储隔离

- `useProjectStorage(key, default)` — 自动按 projectId 后缀隔离 localStorage
- 用于跨页面状态持久化（如日报工作流、优化配置）

### UI 反馈

- `useConfirm()` — `confirmDanger`, `confirmWarn`, `confirmInfo`
- `useToast()` — `notifySuccess`, `notifyError`, `notifyInfo`, `notifyWarning`

## ANTI-PATTERNS

- **禁止** 直接调用 SDK — 必须通过 composable 封装
- **禁止** 在 composable 中使用 `alert()` / `confirm()` — 用 `useConfirm()`
- **禁止** mutation 静默失败 — 必须 `notifyError` + `console.error`
