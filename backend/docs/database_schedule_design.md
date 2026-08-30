# 施工进度管理数据库设计文档

## 概述

本设计实现了施工多目标优化系统的进度管理模块数据库表结构，包括任务管理和依赖关系管理。

## 表结构

### 1. task 表 - 任务表

存储施工工序的基本信息。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 任务唯一标识 |
| code | VARCHAR(20) | NOT NULL, UNIQUE, INDEX | 任务编码，如 TC-001 |
| name | VARCHAR(100) | NOT NULL, INDEX | 任务名称 |
| description | VARCHAR(500) | NULLABLE | 任务详细描述 |
| duration | DOUBLE PRECISION | NOT NULL, CHECK >= 0.5 | 工期（天），最小0.5天 |
| completed | DOUBLE PRECISION | NOT NULL, CHECK 0-1 | 完成度 0-1 |
| created_at | TIMESTAMP | NOT NULL, DEFAULT now() | 创建时间 |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT now() | 更新时间 |

**CHECK 约束:**
- `ck_task_duration_min`: `duration >= 0.5`
- `ck_task_completed_range`: `completed >= 0 AND completed <= 1`

**触发器:**
- `update_task_updated_at`: 在更新前自动更新 `updated_at` 字段

### 2. task_dependency 表 - 任务依赖关系表

存储任务之间的前后置依赖关系。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| task_id | INTEGER | PK, FK(task.id), ON DELETE CASCADE | 当前任务ID |
| predecessor_id | INTEGER | PK, FK(task.id), ON DELETE CASCADE, INDEX | 前置任务ID |
| type | dependencytype | NOT NULL, DEFAULT 'FS' | 依赖类型：FS/SS/FF/SF |
| lag | INTEGER | NOT NULL, DEFAULT 0 | 延迟天数（可负） |

**CHECK 约束:**
- `ck_dependency_no_self_ref`: `task_id != predecessor_id`（防止自引用）

**枚举类型 dependencytype:**
- `FS`: Finish-to-Start (完成-开始)
- `SS`: Start-to-Start (开始-开始)
- `FF`: Finish-to-Finish (完成-完成)
- `SF`: Start-to-Finish (开始-完成)

## 索引设计

| 表 | 索引名 | 字段 | 类型 | 说明 |
|----|--------|------|------|------|
| task | task_pkey | id | PRIMARY KEY | 主键索引 |
| task | ix_task_code | code | UNIQUE | 唯一编码索引 |
| task | ix_task_name | name | INDEX | 名称搜索索引 |
| task_dependency | task_dependency_pkey | task_id, predecessor_id | PRIMARY KEY | 复合主键 |
| task_dependency | ix_task_dependency_predecessor_id | predecessor_id | INDEX | 前置任务外键索引 |

## 设计决策

### 下放到数据库层的功能

1. **默认值和自动更新**
   - `created_at` / `updated_at`: 使用 `server_default=now()`
   - `updated_at` 自动更新: 使用触发器 `update_task_updated_at`

2. **数据完整性约束**
   - CHECK 约束: 工期最小值、完成度范围、禁止自引用
   - 外键约束: 级联删除 (ON DELETE CASCADE)
   - 唯一约束: 任务编码唯一

3. **索引优化**
   - 所有 FK 字段添加索引 (predecessor_id)
   - 查询常用字段添加索引 (code, name, is_critical)

### 在应用层实现的功能

1. **循环依赖检测**
   - 原因: 需要返回详细的循环路径信息给前端
   - 实现: 使用递归 CTE 在 Python 中检测

2. **关键路径计算**
   - 原因: 涉及复杂的图算法（前向/后向传递）
   - 实现: 在应用层通过拓扑排序和动态规划计算

3. **任务编码自动生成**
   - 原因: 需要查询当前最大编码
   - 实现: 在创建任务时自动生成 TC-XXX 格式编码

## Alembic 迁移

迁移文件: `alembic/versions/e4355ed98f9c_create_task_and_task_dependency_tables.py`

迁移说明:
- 使用 SQLModel 自动生成基础表结构
- 手动补充: CHECK 约束、索引（通过 `__table_args__` 已在模型中定义）
- 手动补充: 触发器创建、表和列注释

运行迁移:
```bash
alembic upgrade head
```

## 相关文件

- `src/models/task.py` - SQLModel 数据库模型
- `src/schemas/task.py` - Pydantic Schema 定义
- `alembic/versions/e4355ed98f9c_create_task_and_task_dependency_tables.py` - 数据库迁移
