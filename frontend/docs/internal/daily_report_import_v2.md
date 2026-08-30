---
title: 施工日报导入方案 v2.0 (修复版)
---

# 施工日报导入方案 v2.0

## 一、核心问题修复总结

| 原方案问题                       | 修复方案                         |
| -------------------------------- | -------------------------------- |
| 缺失 resource.name → id 映射逻辑 | 新增智能映射层 + 用户确认流程    |
| 缺失时间维度                     | 新增 date 字段，按日报日期记录   |
| 缺失校验规则                     | 新增多级校验（格式、数量、跨表） |
| 过度设计（临时表）               | 简化方案，前端状态 + 一次性提交  |

---

## 二、完整数据流设计

```mermaid
graph TD
    A[用户上传施工日报 Excel] --> B[解析 Excel<br/>提取 resource.name → usage]
    B --> C{资源名称匹配检查}
    C -->|精确匹配| D[直接使用已有 resource_id]
    C -->|无匹配| E[标记为"待创建"]
    C -->|模糊匹配| F[展示候选列表让用户选择]
    D --> G[用户选择日期]
    E --> G
    F --> G
    G --> H[用户分配资源到工序]
    H --> I{校验通过?}
    I -->|否| J[返回错误信息]
    I -->|是| K[提交入库]
    K --> L[更新 task_resource_usage 表]
```

---

## 三、数据库表设计

### 3.1 最终落地表（核心）

```sql
CREATE TABLE task_resource_usage (
    id SERIAL PRIMARY KEY,
    task_id INT NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    resource_id INT NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL,  -- 新增：日期维度
    quantity DECIMAL(10, 3) NOT NULL CHECK (quantity > 0),
    batch_id UUID NOT NULL,   -- 关联导入批次，用于审计
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(task_id, resource_id, usage_date)  -- 同一工序同一天同一资源只记录一条
);

CREATE INDEX idx_task_resource_usage_date ON task_resource_usage(usage_date);
CREATE INDEX idx_task_resource_usage_task ON task_resource_usage(task_id);
CREATE INDEX idx_task_resource_usage_batch ON task_resource_usage(batch_id);
```

### 3.2 导入批次表（轻量级审计）

```sql
CREATE TABLE import_batch (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_filename VARCHAR(255) NOT NULL,
    usage_date DATE NOT NULL,           -- 日报的日期
    total_rows INT NOT NULL,
    imported_rows INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    -- status: PENDING / PARTIAL / COMPLETED / FAILED
    created_by INT,                     -- 用户ID（如果有）
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);
```

---

## 四、API 接口设计

### 4.1 第一步：上传并解析 Excel

**POST** `/api/v1/daily-report/parse`

**请求**:

```python
class DailyReportParseRequest:
    file: UploadFile  # Excel 文件
    usage_date: date  # 日报所属日期（必填）
```

**响应**:

```python
class DailyReportParseResponse:
    batch_id: UUID
    parsed_items: list[ParsedResourceItem]
    # 示例：
    # [
    #   {
    #     "row_index": 1,
    #     "resource_name": "挖掘机 A 型",
    #     "quantity": 12.0,
    #     "category": "machinery",
    #     "mapping_status": "EXACT_MATCH",  # EXACT_MATCH / FUZZY_MATCH / NEW
    #     "resource_id": 101,  # 如果是 EXACT_MATCH
    #     "candidates": []    # 如果是 FUZZY_MATCH
    #   },
    #   {
    #     "row_index": 2,
    #     "resource_name": "木工",
    #     "quantity": 3.0,
    #     "category": "labor",
    #     "mapping_status": "NEW",
    #     "resource_id": None,
    #     "candidates": []
    #   }
    # ]

class ParsedResourceItem:
    row_index: int
    resource_name: str
    quantity: float
    category: str | None  # 如果能通过名称推断
    mapping_status: Literal["EXACT_MATCH", "FUZZY_MATCH", "NEW"]
    resource_id: int | None
    candidates: list[ResourceCandidate]  # 模糊匹配时的候选
```

### 4.2 第二步：确认资源映射

**POST** `/api/v1/daily-report/confirm-mapping`

**请求**:

```python
class ConfirmMappingRequest:
    batch_id: UUID
    mappings: list[ResourceMappingItem]
    # 示例：
    # [
    #   {"row_index": 1, "action": "USE_EXISTING", "resource_id": 101},
    #   {"row_index": 2, "action": "CREATE_NEW", "new_resource": {"name": "木工", "category": "labor", "unit": "人天", ...}},
    #   {"row_index": 3, "action": "SKIP"}  # 跳过无法识别的行
    # ]

class ResourceMappingItem:
    row_index: int
    action: Literal["USE_EXISTING", "CREATE_NEW", "SKIP"]
    resource_id: int | None  # USE_EXISTING 时
    new_resource: ResourceCreate | None  # CREATE_NEW 时
```

**响应**:

```python
class ConfirmMappingResponse:
    batch_id: UUID
    confirmed_items: list[ConfirmedResourceItem]
    # 返回可用于分配的资源列表
    # [
    #   {
    #     "row_index": 1,
    #     "resource_id": 101,
    #     "resource_name": "挖掘机 A 型",
    #     "quantity": 12.0,
    #     "allocated_quantity": 0.0  # 已分配到工序的数量
    #   },
    #   ...
    # ]
```

### 4.3 第三步：分配资源到工序

**POST** `/api/v1/daily-report/allocate`

**请求**:

```python
class AllocateRequest:
    batch_id: UUID
    allocations: list[AllocationItem]
    # 示例：
    # [
    #   {"row_index": 1, "task_id": 5, "quantity": 8.0},   # 挖掘机分配 8 台班到工序5
    #   {"row_index": 1, "task_id": 6, "quantity": 4.0},   # 剩余 4 台班到工序6
    #   {"row_index": 2, "task_id": 5, "quantity": 3.0}    # 木工 3 人天到工序5
    # ]

class AllocationItem:
    row_index: int
    task_id: int
    quantity: float  # 不能超过该行剩余未分配量
```

**响应**:

```python
class AllocationResponse:
    batch_id: UUID
    allocation_summary: list[AllocationSummary]
    # [
    #   {
    #     "row_index": 1,
    #     "resource_name": "挖掘机 A 型",
    #     "total": 12.0,
    #     "allocated": 12.0,
    #     "remaining": 0.0,
    #     "tasks": [
    #       {"task_id": 5, "task_name": "基础开挖", "quantity": 8.0},
    #       {"task_id": 6, "task_name": "土方回填", "quantity": 4.0}
    #     ]
    #   }
    # ]

class AllocationSummary:
    row_index: int
    resource_name: str
    total: float
    allocated: float
    remaining: float
    tasks: list[TaskAllocation]
```

### 4.4 第四步：提交入库

**POST** `/api/v1/daily-report/submit`

**请求**:

```python
class SubmitRequest:
    batch_id: UUID
    # 前端确认后提交
```

**响应**:

```python
class SubmitResponse:
    batch_id: UUID
    imported_count: int
    task_resource_usage_ids: list[int]
```

---

## 五、资源名称映射策略

### 5.1 映射状态定义

| 状态          | 含义                           | 处理方式                 |
| ------------- | ------------------------------ | ------------------------ |
| `EXACT_MATCH` | 精确匹配（名称完全相同且唯一） | 直接使用已有 resource_id |
| `FUZZY_MATCH` | 模糊匹配（多个候选）           | 让用户选择具体使用哪个   |
| `NEW`         | 数据库中不存在                 | 让用户选择新建或跳过     |

### 5.2 模糊匹配规则

```python
def fuzzy_match(resource_name: str) -> list[Resource]:
    # 1. 去除空格后匹配
    # 2. 包含匹配（部分名称匹配）
    # 3. 同义词匹配（如"挖掘机"↔"挖机"）

    candidates = []

    # 精确匹配
    exact = db.query(Resource).filter(Resource.name == resource_name).all()
    if len(exact) == 1:
        return {"status": "EXACT_MATCH", "resource_id": exact[0].id}
    if len(exact) > 1:
        return {"status": "FUZZY_MATCH", "candidates": exact}

    # 包含匹配
    partial = db.query(Resource).filter(
        Resource.name.contains(resource_name) |
        Resource.description.contains(resource_name)
    ).all()

    if partial:
        return {"status": "FUZZY_MATCH", "candidates": partial}

    return {"status": "NEW", "candidates": []}
```

### 5.3 用户操作界面流程

```
┌─────────────────────────────────────────────────────────┐
│  施工日报解析结果                                        │
├─────────────────────────────────────────────────────────┤
│  📅 日期：2026-03-05 (从文件名/内容提取)                 │
│                                                         │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 资源名称      │ 数量  │ 状态        │ 操作       │  │
│  ├─────────────────────────────────────────────────┤  │
│  │ 挖掘机 A 型   │ 12    │ ✓ 精确匹配   │ [确认]     │  │
│  │ 木工          │ 3     │ ⚠ 新建资源   │ [新建][跳过]│  │
│  │ 钢筋工        │ 4     │ ⚠ 模糊匹配   │ [选择]     │  │
│  └─────────────────────────────────────────────────┘  │
│                                                         │
│  [上一步]                        [下一步：分配到工序]    │
└─────────────────────────────────────────────────────────┘
```

---

## 六、校验规则

### 6.1 行内校验（单行级别）

| 规则         | 说明                    | 处理       |
| ------------ | ----------------------- | ---------- |
| 数量 > 0     | 使用量必须为正数        | 拒绝       |
| 数量合理性   | 超过阈值（如99999）警告 | 警告但允许 |
| 资源名称非空 | 不能为空字符串          | 拒绝       |

### 6.2 跨行校验（批次级别）

| 规则       | 说明                          | 处理                 |
| ---------- | ----------------------------- | -------------------- |
| 分配完整性 | 所有资源必须分配完            | 允许部分分配（提示） |
| 任务存在性 | task_id 必须存在于数据库      | 拒绝                 |
| 数量守恒   | 同一行的分配量之和 ≤ 原始数量 | 拒绝超额             |
| 日期合法性 | 不能是未来日期                | 警告                 |

### 6.3 业务校验

| 规则              | 说明                                         |
| ----------------- | -------------------------------------------- |
| 资源-任务合理配对 | 如"材料"类资源不应分配给纯"人工"工序（可选） |
| 数量单位匹配      | 资源单位与使用量匹配（可选）                 |

---

## 七、错误处理

### 7.1 错误响应格式

```python
class ImportErrorResponse:
    error_code: str
    message: str
    details: list[ErrorDetail] | None

class ErrorDetail:
    row_index: int | None
    field: str
    message: str
```

### 7.2 常见错误码

| 错误码                 | 说明                       |
| ---------------------- | -------------------------- |
| `INVALID_FILE`         | 文件格式不支持             |
| `PARSE_FAILED`         | Excel 解析失败             |
| `RESOURCE_NOT_FOUND`   | 资源不存在且用户未创建     |
| `TASK_NOT_FOUND`       | 分配的任务不存在           |
| `QUANTITY_EXCEED`      | 分配量超过可用量           |
| `DUPLICATE_ALLOCATION` | 重复分配同一资源到同一任务 |

---

## 八、与原方案对比

| 维度     | 原方案 (excel_parse_to_db.md) | 新方案 (v2.0)             |
| -------- | ----------------------------- | ------------------------- |
| 资源映射 | ❌ 完全忽略                   | ✅ 智能映射 + 用户确认    |
| 时间维度 | ❌ 无                         | ✅ 按日记录               |
| 校验规则 | ❌ 无                         | ✅ 多级校验               |
| 临时表   | ✅ 过度设计                   | ✅ 简化为单批次表         |
| 状态管理 | Postgres 临时表               | 前端状态 + 一次性提交     |
| 审计追溯 | batch_id                      | import_batch 表（更完整） |

---

## 九、关键设计决策说明

### 9.1 为什么不使用临时表？

- **数据量小**：施工日报低频操作（可能几天一次），每次 <5k 行
- **用户体验**：现代浏览器 localStorage 足够存储用户分配状态
- **简化架构**：避免临时表过期、清理等运维负担
- **事务保证**：最终提交使用数据库事务保证原子性

### 9.2 为什么需要 usage_date？

CCT.md 明确要求输入数据是 **"工序资源使用（工序，日期，资源，使用量）"**。没有日期：

- 无法按月/按周统计资源消耗
- 无法与工序完成度（按月输入）进行时间对齐
- 无法计算项目历史碳排放/成本趋势

### 9.3 资源映射为什么需要用户参与？

- **命名歧义**："木工"可能指"木工人力"也可能指"木工机械"
- **数据质量**：施工日报可能存在拼写错误
- **业务知识**：某些资源可能是项目专属，不在标准库中

---

## 十、总结

> **"用智能映射解决 name→id 难题，用日期维度满足 CCT.md 需求，用多级校验保障数据质量，用简化架构降低维护成本。"**

本方案在原方案基础上补全了：

1. ✅ 资源名称到 ID 的智能映射逻辑
2. ✅ 时间维度（usage_date）
3. ✅ 完整的校验规则体系
4. ✅ 简化的架构设计（去除过度设计的临时表）
5. ✅ 清晰的 API 接口设计
