# 优化模块 API 数据结构

## 输入数据 (RunConfig)

| 字段             | 类型   | 说明                                   |
| ---------------- | ------ | -------------------------------------- |
| popSize          | number | 种群大小，默认 50                      |
| maxGen           | number | 最大代数，默认 100                     |
| irr              | number | 名义年利率                             |
| acceleratedRatio | number | 加速工期比例，加速施工时工期乘以此比例 |
| maxOffset        | number | 任务开始时间最大偏移量（天）           |

## 输出数据 (OptimizeSolution)

| 字段       | 类型                          | 说明                  |
| ---------- | ----------------------------- | --------------------- |
| id         | number                        | 解 ID                 |
| runId      | string                        | 对应的优化任务运行 ID |
| strategies | TaskStrategy[]                | 各任务的执行策略      |
| cost       | number                        | 现值成本              |
| emission   | number                        | 碳排放                |
| duration   | number                        | 总工期                |
| violations | ResourceConstraintViolation[] | 资源限制违反量        |

## TaskStrategy

| 字段   | 类型     | 说明                                               |
| ------ | -------- | -------------------------------------------------- |
| taskId | number   | 工序 ID                                            |
| mode   | TaskMode | 执行策略模式：0=普通, 1=加速, 2=低碳, 3=加速且低碳 |
| start  | number   | 开始时间                                           |

## API 端点

- `POST /optimize` - 创建优化任务，返回 runId
- `GET /optimize/{id}/running_status` - 获取运行状态
- `GET /optimize/{id}/result` - 获取优化结果（帕累托解集）
- `PATCH /optimize/{id}?abort=true` - 中止优化
- `DELETE /optimize/{id}` - 删除优化记录
- `GET /optimize` - 列出历史优化记录

## 优化状态 (RunStatusEnum)

- PENDING - 等待中
- RUNNING - 运行中（有 currGen/maxGen 进度）
- SUCCESS - 成功完成
- FAILURE - 运行失败（errorMsg 包含错误信息）
