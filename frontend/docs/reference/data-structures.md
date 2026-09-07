# 数据结构速查

本文以 JSON 形式罗列软件中的核心数据结构，帮助使用者理解各页面展示的数据来源与字段含义。

::: tip
数据通过后端 OpenAPI 规范自动生成类型安全的 API 客户端，前端直接使用这些结构，无需手工转换。
:::

## 项目（Project）

```json
{
  "id": 1,
  "name": "某商业综合体项目",
  "description": "示例",
  "is_active": true,
  "land_area": 12000.0,
  "building_area": 86000.0,
  "province": "浙江省",
  "city": "杭州市",
  "address": "某区某路 1 号",
  "underground_building_area": 26000.0,
  "aboveground_building_area": 60000.0,
  "structure_types": ["框架结构", "剪力墙结构"],
  "prefabrication_rate": 0.35,
  "design_service_life": 50,
  "structural_safety_level": "二级",
  "planned_start_date": "2025-03-01",
  "planned_completion_date": "2027-06-30",
  "construction_carbon_emission_limit": 500000.0,
  "housing_resource_id": 105,
  "housing_safety_factor": 1.2,
  "persons_per_room": 4
}
```

## 任务（Task）与依赖（TaskDependency）

```json
// 任务（含标签）
{
  "id": 1,
  "code": "AUTO-1",
  "name": "基坑开挖",
  "description": null,
  "duration": 10.0,
  "completed": 0.0,
  "is_critical": true,
  "predecessors": [
    { "taskId": 1, "predecessorId": 3, "type": "FS" }
  ],
  "tags": []
}

// 进度统计
{ "totalTasks": 12, "totalDuration": 96.0, "criticalDuration": 55.0 }
```

## 资源（Resource）与公共资源（ResourcePublic）

```json
// 项目资源
{
  "id": 101,
  "name": "挖掘机 A 型",
  "category": "machinery", // labor/machinery/material/transport/others
  "unit": "台班",
  "unit_price": 1500.0,
  "carbon_factor": 50.0,
  "description": "SE135-9W"
}

// 公共资源（全局只读字典，字段同项目资源）
// 拷贝到项目：POST /public-resource/batch-copy
// 响应：{ "copied": [...], "skipped": [...], "notFound": [...] }
```

## 资源使用（TaskResourceUsage）

```json
{
  "id": 2001,
  "taskId": 5,
  "resourceId": 101,
  "usageDate": "2025-12-14",
  "quantity": 4.0,
  "usageType": "ACTUAL", // ACTUAL 实际 / PLANNED 计划
  "batchId": "3f2a9c10-...", // 日报导入批次（可空）
  "manualBatchId": 7 // 手动录入批次（可空）
}
```

## 日报批次（ImportBatch）

```json
{
  "id": "3f2a9c10-...",
  "originalFilename": "20251214蚂蚁二期施工日报.xlsx",
  "usageDate": "2025-12-14",
  "totalRows": 26,
  "importedRows": 26,
  "status": "COMPLETED",        // PENDING/MAPPING/ALLOCATING/COMPLETED/FAILED
  "parsedItems": [...],         // 解析条目（JSON）
  "confirmedItems": [...],      // 确认映射条目（JSON）
  "allocatedItems": [...],      // 分配条目（JSON）
  "warnings": []                // 解析警告
}
```

## 优化运行（OptimizationRun）与帕累托解（ParetoSolution）

```json
// 运行（含任务/依赖快照，运行后修改工序不影响历史回放）
{
  "id": "3f2a9c10-...",
  "name": "串行 #1",
  "status": "SUCCESS",
  "currGen": 100,
  "maxGen": 100,
  "popSize": 100,
  "irr": 0.05,
  "acceleratedRatio": 0.8,
  "maxOffset": 60,
  "usageType": "ACTUAL",
  "taskSnapshot": [{ "id": 1, "code": "AUTO-1", "name": "基坑开挖", "duration": 10.0 }],
  "dependencySnapshot": [{ "taskId": 2, "predecessorId": 1, "type": "FS" }]
}

// 帕累托解
{
  "id": 1,
  "runId": "3f2a9c10-...",
  "cost": 386.5,             // 现值成本（万元）
  "emission": 1240.6,        // 碳排放（t）
  "duration": 55.0,          // 总工期（天）
  "strategies": [
    { "taskId": 1, "mode": 0, "start": 0 },
    { "taskId": 2, "mode": 1, "start": 10 }
  ],
  "violations": [
    { "resourceId": 101, "maxUsage": 5.0, "realUsage": 6.2, "overage": 1.2 }
  ],
  "peakPersonnel": 96,
  "housingRooms": 29
}
```

## 资源约束（ResourceConstraint）与周转配置（ResourceReuseConfig）

```json
// 约束：资源日用量上限
{
  "id": 1,
  "resourceId": 101,
  "maxUsage": 5.0,
  "description": "挖掘机每日最多 5 台班"
}

// 周转配置：材料复用折减
{
  "id": 1,
  "resourceId": 102,
  "maxReuses": 10,
  "reuseCount": 3,
  "affectCost": false,
  "description": "模板周转"
}
```

## 标签系统（Tag / Chart / Slice）

```json
// 标签（扁平，名称项目内唯一）
{
  "id": 11,
  "name": "施工用材",
  "group": "建材",       // 纯展示分组，"" = 未分组
  "description": "",
  "isDefault": false     // true = 「资源类别」默认标签（人工/机械/材料/运输/其他）
}

// 关联：资源标签 / 任务标签 / 用量标签
// { resourceId|taskId|usageId, tagIds: [11, 12] }
// 注意：默认分类标签不可手工打标（分类语义由资源类别自动命中）

// 图表定义（含切片；标签均为项目内真实正 id）
{
  "id": 1,
  "name": "施工用材占比",
  "chartType": "PIE",
  "slices": [
    {
      "id": 21,
      "name": "地下工程支护",
      "sortOrder": 0,
      "tags": [
        { "tagId": 11, "tagName": "施工用材", "group": 0 },
        { "tagId": 5,  "tagName": "材料",     "group": 0 }
      ]
    }
  ]
}

// 饼图数据（每个 slice 一个切片 = 命中该切片标签组的用量聚合；value 为 kgCO2e 或元）
[{ "name": "地下工程支护", "value": 45230.5, "sortOrder": 0 }]
```

切片命中：同 `group` 内标签需**同时**命中（且），不同 `group` 之间命中任一（或）；
用量行的合并标签 = 资源/任务/用量三类实体标签 ∪ 资源分类显示名（按名称去重，与
「资源类别」默认标签同名），来源为 `usage_snapshot` 物化视图（约 30 分钟自动刷新，
可手动刷新）。切片引用默认标签行即可实现「只统计某类资源」的过滤。

## 通用约定

| 约定     | 说明                                                              |
| -------- | ----------------------------------------------------------------- |
| 分页     | 列表接口统一返回 `{ items: [...], total: N }`                     |
| 命名     | 接口字段使用 camelCase（如 `maxUsage`、`usageType`）              |
| 单位     | 成本接口多为元或万元（前端统一按万元显示）；碳排放 kg（解集为 t） |
| 部分更新 | 更新接口使用 PUT，缺省字段保持不变；显式 null 仅对可空字段有效    |
| 项目隔离 | 所有业务实体通过 `project_id` 归属项目，接口路径含 `{project_id}` |
