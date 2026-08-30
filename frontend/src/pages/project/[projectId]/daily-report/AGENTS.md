# Daily Report Workflow

## OVERVIEW

5步向导式日报处理流程：导入 → 审核 → 分配 → 确认 → 完成。

## STRUCTURE

```
daily-report/
├── index.vue      # 重定向到 import
├── import.vue     # 上传解析日报
├── review.vue     # 审核资源映射 (复杂)
├── allocate.vue   # 分配资源到工序
├── confirm.vue    # 确认提交
└── success.vue    # 成功页面
```

## WHERE TO LOOK

| 功能         | 文件                                                        |
| ------------ | ----------------------------------------------------------- |
| 解析逻辑     | `import.vue` → `useDailyReportApi.parseDailyReport()`       |
| 映射状态管理 | `stores/report.ts` → `parsedResources`, `mappingStatus`     |
| 资源映射决策 | `review.vue` → `USE_EXISTING/CREATE_NEW/SKIP`               |
| 分配数量计算 | `allocate.vue` → `getRemaining()`, `getAvailableQuantity()` |
| 工作流状态   | `stores/report.ts` (`useDailyReportStoreV2`) — 全局状态协调 |

## CONVENTIONS

### 状态管理

- Pinia store (`report.ts`) 管理跨页面状态
- 每步完成后 `router.push('/daily-report/next-step')`
- 完成后调用 `store.reset()` 清理
- 状态持久化：`@vueuse/core` 的 `useStorage`

### 资源映射状态

```
EXACT_MATCH  → 直接使用 resourceId
FUZZY_MATCH  → 用户选择候选资源
NEW          → 创建新资源或跳过
```

### 数量分配

- 使用 `Map<resourceId, quantity>` 存储分配
- `remainingResources` computed 实时计算剩余
