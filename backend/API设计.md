# 碳排放展示需求

我计划实现一个标签系统，用于区分碳排放类别；再实现一套图定义系统，用来定义需要展示的图表。

比如说，我希望（在软件使用阶段）定义多个饼图，例如：
1. 施工用材各部分占比：包含 tag：地下工程支护、主体工程支护、辅材、临建设施
2. 施工现场各部分占比：包含 tag：施工区外购电力、生活区外购电力、光伏发电、外购自来水、柴油
3. 施工运输各部分占比（全部展开）：建材（按 task）、施工用材、生活垃圾、建筑垃圾、渣土
4. 施工各部分占比：三块，用材、运输、现场
5. 碳排放来源占比：建材（最终建筑物材料）、施工用材、施工机械、临建与水电消耗、施工运输
6. 运输各部分占比：材料运输、生活垃圾、建筑垃圾、渣土外运

**常见难点**：同一材料（如"钢支护"）被"主体支护工程""地下支护工程"两个工序共用、
同一运输工具（如"重型卡车"）运输多种货物——按资源打标无法正确切分，归属必须下沉到
任务 / 用量粒度；且"工序""位置"等多套分类应各自独立成树。

# 解决方案（标签系统 v2）

## 核心抽象

- **标签维度（TagDimension）**：项目内可有多个维度（如"碳排放来源""运输货物""地理位置"），
  每个维度是一棵独立的标签树；标签名称唯一 = `(project, dimension, name)`，父标签必须同维度。
- **三个打标关联点**：资源（`resource_tag`）、任务（`task_tag`）、**用量**（`usage_tag`，A2）。
  同一实体可跨维度打多个标签。
- **图表切片归属实体（slice_entity）**：`RESOURCE` / `TASK` / `USAGE` / `ANY`，
  决定饼图聚合以哪类标签为准；另可配 `resource_categories`（material/transport/energy…）过滤资源类型。
- **打标互斥校验**：按"切片子树集合"判定，任何实体的标签（ANY 图还含关联实体标签）
  不得命中同一图表的两个切片——从源头保证饼图不虚增（含父+子标签同为切片的场景）。

## 数据库表结构

```python
# src/models/tag.py —— 标签维度（项目内 name 唯一）
class TagDimension(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    __tablename__ = "tag_dimension"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "name", name="uix_tag_dimension_project_name"),
    )
    id: int | None          # PK
    name: str               # 维度名称，如：碳排放来源
    description: str

# src/models/tag.py —— 标签（维度内 name 唯一，同维度成树）
class Tag(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    __tablename__ = "tag"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "dimension_id", "name",
                            name="uix_tag_project_dimension_name"),
    )
    id: int | None
    name: str
    dimension_id: int       # FK tag_dimension.id CASCADE，父标签须同维度
    parent_id: int | None   # 自引用 FK；null = 顶级
    description: str

# src/models/tag.py —— 三个打标关联点（结构一致，仅关联对象不同）
class ResourceTag(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):  # 已有
    __tablename__ = "resource_tag"     # UNIQUE(project_id, resource_id, tag_id)
    resource_id / tag_id

class TaskTag(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    __tablename__ = "task_tag"         # UNIQUE(project_id, task_id, tag_id)
    task_id / tag_id                   # INDEX(project_id, tag_id, task_id) 供聚合

class UsageTag(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    __tablename__ = "usage_tag"        # UNIQUE(project_id, usage_id, tag_id)
    usage_id / tag_id                  # INDEX(project_id, tag_id) 供聚合

# src/models/chart.py —— 图表定义（新增切片配置）
class ChartDefinition(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    __tablename__ = "chart_definition" # UNIQUE(project_id, name)
    id / name / description / chart_type
    slice_entity: str                  # RESOURCE/TASK/USAGE/ANY，默认 RESOURCE（兼容旧图）
    resource_categories: list | None   # JSON；material/transport/... 过滤，null=不过滤
```

## 核心查询逻辑（以项目为单位）

与旧版一致采用 **Python 展开标签子树 + 逐切片聚合 SQL**（一次加载项目全量标签构建
内存树 DFS 收集子孙，避免递归 CTE）。每个切片 = 绑定标签自身及其全部子孙标签的碳排放总和。

聚合按 `slice_entity` 分支，用 `EXISTS` 判定命中（避免 JOIN 造成 quantity 重复加总）：

```python
# src/services/carbon_chart.py（伪代码）
if slice_entity == "TASK":
    hit = EXISTS(task_tag WHERE task_id = usage.task_id AND tag_id IN subtree)
elif slice_entity == "USAGE":
    hit = EXISTS(usage_tag WHERE usage_id = usage.id AND tag_id IN subtree)
elif slice_entity == "ANY":
    hit = 资源 EXISTS OR 任务 EXISTS OR 用量 EXISTS
else:  # RESOURCE（默认，兼容旧图）
    hit = EXISTS(resource_tag WHERE resource_id = usage.resource_id AND tag_id IN subtree)
```

- 可选 `resource_categories`：`WHERE resource.category IN (...)`。
- 碳排放口径与月度报表一致：SQL 只聚合 `SUM(quantity)`，Python 层应用
  `ResourceReuseConfig` 周转折减后计算排放。
- 仍支持 `usageType` / `startDate` / `endDate` 过滤。

## 打标互斥校验（防虚增核心）

`src/services/tag_validation.py` 的 `ChartConflictValidator`：

- 按实体类型（resource/task/usage）× 图表 slice_entity 匹配校验范围。
- 对每个图表，先把其绑定的每个标签展开成子树集合；再计算实体的标签（含已有标签）
  命中哪些切片——**命中 ≥2 个切片即拒绝（409）**。
- 覆盖旧版漏掉的场景：图同时绑定父+子标签时，只打子标签也会被子树展开双计，同样拦截。
- ANY 图表额外纳入关联实体标签（同一用量的资源/任务/用量标签），
  保证"资源打 A 切片、它的用量打 B 切片"这种组合也会被拦截。

## 打标 API

- `PUT /projects/{pid}/resource/{resource_id}/tags`（已有）
- `PUT /projects/{pid}/task/{task_id}/tags`（新）
- `PUT /projects/{pid}/resource-usage/{usage_id}/tags`（新，替换式，日报导入的用量同样可改）

## 日报导入（运输块 A2）

- `src/utils/daily_report_config.json` 新增 `transport` 块：行结构
  `货物类别 / 运输工具 / 车次`，解析出的条目带 `cargo` 字段
  （去重键 = `(名称, cargo)`，同名不同货物可并存）。
- `cargo` 贯穿 parse → confirm-mapping → allocate → submit；
  submit 落库时按 cargo 名称精确匹配项目内「运输货物」维度标签并写入 `usage_tag`，
  **匹配不到则跳过**（不阻断导入），用户可事后用 `PUT /resource-usage/{id}/tags` 补标。
- 同一 (任务, 车辆) 存在多种货物类别时提交失败，避免触碰
  `(project, task, resource, date, type)` 唯一约束或静默丢标。

## 迁移说明

`c3f9d2e1a4b5`：建 `tag_dimension` / `task_tag` / `usage_tag`；`tag` 加 `dimension_id`
（NOT NULL）；名称唯一约束改为按维度；`chart_definition` 加 `slice_entity` /
`resource_categories`。**开发期清理**：删除旧标签/图表数据（不再回填默认维度）。

## 六图配置示例（能力已就绪，维度/标签由用户配置）

| 图 | sliceEntity | 切片（维度） | resourceCategories |
|---|---|---|---|
| 1 施工用材占比 | RESOURCE | 来源维：施工用材 4 子 | [material] |
| 2 施工现场占比 | RESOURCE | 来源维：水电消耗 4 子 | [energy] |
| 3 运输占比（全展开） | USAGE | 运输货物维：建材按任务 / 施工用材 / 生活垃圾 / 建筑垃圾 / 渣土 | [transport] |
| 6 运输各部分 | USAGE | 运输货物维：[材料运输, 生活垃圾, 建筑垃圾, 渣土] | [transport] |
| 4 施工各部分 | RESOURCE | 来源维：[施工用材, 施工运输, 水电消耗] | — |
| 5 碳排放来源 | RESOURCE | 来源维：[建材, 施工机械, 施工用材与水电消耗, 施工运输] | — |

「碳排放来源」维度树：

```
碳排放来源
├── 建材（最终建筑物材料）
├── 施工机械
├── 施工用材与水电消耗
│   ├── 施工用材 → [地下工程支护, 主体工程支护, 辅材, 临建设施]
│   └── 水电消耗 → [外购电力, 外购自来水, 柴油, 光伏发电]
└── 施工运输
```

「运输货物」维度树（打标：用量）：`材料运输 → [建材 → 按 task（土方工程通常为 0）,
施工用材 → [4 类]], 生活垃圾, 建筑垃圾, 渣土`。

「地理位置」维度（生活区/施工区）预留：任务+资源均可打标，未来现场 6 分图
（水/电分生活区/施工区）用 ANY 模式实现。
