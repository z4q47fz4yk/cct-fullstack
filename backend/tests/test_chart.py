"""碳排放图表定义与饼图数据 API 测试。"""
# pyright: reportCallIssue=false

from datetime import date
from typing import cast

import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.tag import ResourceTag, Tag, TagDimension, TaskTag, UsageTag
from src.models.task import Task
from src.schemas.resource import ResourceCategory


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    """测试项目（CurrentProject 依赖需要）。"""
    p = Project(name="Chart Test Project", is_active=True)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def dimension(db_session: AsyncSession, project: Project) -> TagDimension:
    d = TagDimension(project_id=cast(int, project.id), name="默认维度", description="d")
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    return d


@pytest_asyncio.fixture
async def tags(
    db_session: AsyncSession,
    project: Project,
    dimension: TagDimension,
) -> dict[str, Tag]:
    """标签树（对应需求示例）：

    施工用材(t1) → 地下工程支护(t1_1) / 主体工程支护(t1_2)
    施工运输(t2) → 地下室工程(t2_1)
    """
    pid = project.id
    did = dimension.id
    assert pid is not None and did is not None
    t1 = Tag(project_id=pid, dimension_id=did, name="施工用材", description="d")
    t2 = Tag(project_id=pid, dimension_id=did, name="施工运输", description="d")
    db_session.add_all([t1, t2])
    await db_session.commit()
    await db_session.refresh(t1)
    await db_session.refresh(t2)
    t1_1 = Tag(
        project_id=pid,
        dimension_id=did,
        name="地下工程支护",
        parent_id=t1.id,
        description="d",
    )
    t1_2 = Tag(
        project_id=pid,
        dimension_id=did,
        name="主体工程支护",
        parent_id=t1.id,
        description="d",
    )
    t2_1 = Tag(
        project_id=pid,
        dimension_id=did,
        name="地下室工程",
        parent_id=t2.id,
        description="d",
    )
    db_session.add_all([t1_1, t1_2, t2_1])
    await db_session.commit()
    for t in (t1_1, t1_2, t2_1):
        await db_session.refresh(t)
    return {"t1": t1, "t1_1": t1_1, "t1_2": t1_2, "t2": t2, "t2_1": t2_1}


@pytest_asyncio.fixture
async def resources(db_session: AsyncSession, project: Project) -> list[Resource]:
    pid = project.id
    assert pid is not None
    rs = [
        Resource(
            project_id=pid,
            name=f"R{i}",
            description="d",
            category=ResourceCategory.material,
            carbon_factor=cf,
        )
        for i, cf in ((1, 2.0), (2, 3.0), (3, 5.0))
    ]
    db_session.add_all(rs)
    await db_session.commit()
    for r in rs:
        await db_session.refresh(r)
    return rs


@pytest_asyncio.fixture
async def task(db_session: AsyncSession, project: Project) -> Task:
    pid = project.id
    assert pid is not None
    t = Task(project_id=pid, code="TC-001", name="T1", duration=5.0)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def usages(
    db_session: AsyncSession,
    project: Project,
    resources: list[Resource],
    task: Task,
) -> list[TaskResourceUsage]:
    """碳排放数值表（cf: r1=2.0, r2=3.0, r3=5.0）：

    Jan r1 ACTUAL  qty=10   → 20.0
    Jan r2 ACTUAL  qty=10   → 30.0
    Jan r3 ACTUAL  qty=4    → 20.0
    Feb r1 PLANNED qty=100  → 200.0（仅 PLANNED，用于排除验证）
    """
    pid = project.id
    tid = task.id
    r1, r2, r3 = (cast(int, r.id) for r in resources)
    assert pid is not None and tid is not None
    rows = [
        TaskResourceUsage(
            project_id=pid,
            task_id=tid,
            resource_id=r1,
            usage_date=date(2026, 1, 10),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=tid,
            resource_id=r2,
            usage_date=date(2026, 1, 12),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=tid,
            resource_id=r3,
            usage_date=date(2026, 1, 14),
            quantity=4.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=tid,
            resource_id=r1,
            usage_date=date(2026, 2, 5),
            quantity=100.0,
            usage_type=UsageType.PLANNED,
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return rows


@pytest_asyncio.fixture
async def tag_links(
    db_session: AsyncSession,
    project: Project,
    tags,
    resources: list[Resource],
):
    """资源打标：r1→地下工程支护；r2→施工用材+主体工程支护（双标签防重）；
    r3→地下室工程。"""
    pid = project.id
    assert pid is not None
    links = [
        (resources[0].id, tags["t1_1"].id),
        (resources[1].id, tags["t1"].id),
        (resources[1].id, tags["t1_2"].id),
        (resources[2].id, tags["t2_1"].id),
    ]
    db_session.add_all([
        ResourceTag(project_id=pid, resource_id=cast(int, rid), tag_id=tid)
        for rid, tid in links
    ])
    await db_session.commit()


async def _create_chart_with_tags(
    client: AsyncClient,
    project_id: int,
    name: str,
    tag_keys: list[str],
    tags: dict[str, Tag],
) -> int:
    """通过 API 创建图表并绑定标签（数组顺序即 sortOrder）。"""
    resp = await client.post(f"/projects/{project_id}/chart", json={"name": name})
    assert resp.status_code == 201
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{project_id}/chart/{chart_id}/tags",
        json={"tagIds": [tags[k].id for k in tag_keys]},
    )
    assert resp.status_code == 200
    return chart_id


# ============================================================
# 图表 CRUD
# ============================================================


async def test_create_chart(client: AsyncClient, project: Project):
    resp = await client.post(
        f"/projects/{project.id}/chart", json={"name": "施工用材各部分占比"}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "施工用材各部分占比"
    assert data["chartType"] == "PIE"
    assert data["tags"] == []


async def test_create_chart_duplicate_name_409(client: AsyncClient, project: Project):
    pid = project.id
    await client.post(f"/projects/{pid}/chart", json={"name": "图A"})
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图A"})
    assert resp.status_code == 409


async def test_list_charts(client: AsyncClient, project: Project, tags):
    pid = cast(int, project.id)
    await _create_chart_with_tags(client, pid, "图A", ["t1_1"], tags)
    await _create_chart_with_tags(client, pid, "图B", ["t2"], tags)
    resp = await client.get(f"/projects/{pid}/chart")
    assert resp.status_code == 200
    body = resp.json()
    names = {it["name"] for it in body["items"]}
    assert {"图A", "图B"} <= names


async def test_get_chart_includes_tags(client: AsyncClient, project: Project, tags):
    pid = cast(int, project.id)
    chart_id = await _create_chart_with_tags(client, pid, "图A", ["t1_1", "t1"], tags)
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert [(t["tagId"], t["sortOrder"]) for t in body["tags"]] == [
        (tags["t1_1"].id, 0),
        (tags["t1"].id, 1),
    ]


async def test_get_chart_404(client: AsyncClient, project: Project):
    resp = await client.get(f"/projects/{project.id}/chart/999999")
    assert resp.status_code == 404


async def test_update_chart(client: AsyncClient, project: Project):
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图A"})
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}", json={"name": "图B", "chartType": "BAR"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "图B"
    assert data["chartType"] == "BAR"


async def test_delete_chart(client: AsyncClient, project: Project):
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图A"})
    chart_id = resp.json()["id"]
    resp = await client.delete(f"/projects/{pid}/chart/{chart_id}")
    assert resp.status_code == 204
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}")
    assert resp.status_code == 404


async def test_set_chart_tags_missing_422(client: AsyncClient, project: Project, tags):
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图A"})
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/tags",
        json={"tagIds": [tags["t1"].id, 999999]},
    )
    assert resp.status_code == 422


# ============================================================
# 饼图数据
# ============================================================


async def test_pie_data_leaf_chart(
    client: AsyncClient,
    project: Project,
    tags,
    usages,
    tag_links,
):
    """图1（施工用材各部分占比）：绑定两个叶子标签 → 各自独立切片。"""
    pid = cast(int, project.id)
    chart_id = await _create_chart_with_tags(client, pid, "图1", ["t1_1", "t1_2"], tags)

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    slices = {s["name"]: s["value"] for s in resp.json()}
    assert slices == {"地下工程支护": 20.0, "主体工程支护": 30.0}


async def test_pie_data_root_chart_aggregates_subtree(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    usages,
    tag_links,
):
    """图4（施工过程各部分占比）：绑定父标签 → 每块汇总整棵子树，仅 3 大块。

    r2 同时打了"施工用材"与其子"主体工程支护"，验证 EXISTS 防重复
    （施工用材切片 = 20.0 + 30.0 = 50.0，不虚增）。
    """
    pid = cast(int, project.id)
    chart_id = await _create_chart_with_tags(client, pid, "图4", ["t1", "t2"], tags)

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    slices = {s["name"]: s["value"] for s in resp.json()}
    assert slices == {"施工用材": 50.0, "施工运输": 20.0}


async def test_pie_data_usage_type_planned(
    client: AsyncClient,
    project: Project,
    tags,
    usages,
    tag_links,
):
    """usageType=PLANNED → 仅统计计划用量（Feb r1 qty=100 → 200.0）。"""
    pid = cast(int, project.id)
    chart_id = await _create_chart_with_tags(client, pid, "计划图", ["t1_1"], tags)

    resp = await client.get(
        f"/projects/{pid}/chart/{chart_id}/pie-data?usageType=PLANNED"
    )
    assert resp.status_code == 200
    assert resp.json() == [{"name": "地下工程支护", "value": 200.0, "sortOrder": 0}]


async def test_pie_data_default_actual_only(
    client: AsyncClient,
    project: Project,
    tags,
    usages,
    tag_links,
):
    """默认仅统计 ACTUAL：PLANNED 的 200.0 被排除。"""
    pid = cast(int, project.id)
    chart_id = await _create_chart_with_tags(client, pid, "实际图", ["t1_1"], tags)

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    assert resp.json() == [{"name": "地下工程支护", "value": 20.0, "sortOrder": 0}]


async def test_pie_data_date_window(
    client: AsyncClient,
    project: Project,
    tags,
    usages,
    tag_links,
):
    """日期窗口过滤：startDate=2026-02-01 起无 ACTUAL 数据 → 切片 0.0。"""
    pid = cast(int, project.id)
    chart_id = await _create_chart_with_tags(client, pid, "日期图", ["t1_1"], tags)

    resp = await client.get(
        f"/projects/{pid}/chart/{chart_id}/pie-data?startDate=2026-02-01"
    )
    assert resp.status_code == 200
    assert resp.json() == [{"name": "地下工程支护", "value": 0.0, "sortOrder": 0}]


async def test_pie_data_empty_chart(
    client: AsyncClient,
    project: Project,
    tags,
    usages,
    tag_links,
):
    """图表未绑定任何标签 → 空列表。"""
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "空图"})
    chart_id = resp.json()["id"]
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_pie_data_chart_404(client: AsyncClient, project: Project):
    resp = await client.get(f"/projects/{project.id}/chart/999999/pie-data")
    assert resp.status_code == 404


async def test_pie_data_applies_reuse_config(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resources: list[Resource],
    task: Task,
):
    """饼图口径与月度报表一致：应用资源周转折减（max_reuses=2 → 因子减半）。"""
    pid = project.id
    r1 = resources[0]
    assert pid is not None and r1.id is not None and task.id is not None
    db_session.add(
        TaskResourceUsage(
            project_id=pid,
            task_id=task.id,
            resource_id=r1.id,
            usage_date=date(2026, 1, 10),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        )
    )
    db_session.add(
        ResourceReuseConfig(
            project_id=pid,
            resource_id=r1.id,
            max_reuses=2,
            reuse_count=1,
            affect_cost=False,
            description="d",
        )
    )
    db_session.add(
        ResourceTag(project_id=pid, resource_id=r1.id, tag_id=tags["t1_1"].id)
    )
    await db_session.commit()

    chart_id = await _create_chart_with_tags(client, pid, "折减图", ["t1_1"], tags)
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    # 因子 2.0 / (2*1) = 1.0 → 10 * 1.0 = 10.0
    assert resp.json() == [{"name": "地下工程支护", "value": 10.0, "sortOrder": 0}]


# ============================================================
# 图表 sliceEntity / resourceCategories
# ============================================================


async def test_create_chart_with_slice_config(client: AsyncClient, project: Project):
    resp = await client.post(
        f"/projects/{project.id}/chart",
        json={
            "name": "运输占比图",
            "sliceEntity": "USAGE",
            "resourceCategories": ["transport"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sliceEntity"] == "USAGE"
    assert data["resourceCategories"] == ["transport"]


async def test_pie_data_usage_mode(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    usages,
):
    """USAGE 模式：切片按用量标签聚合（运输货物分类场景）。"""
    pid = cast(int, project.id)
    u1, u2, _u3, _u4 = usages
    db_session.add_all([
        UsageTag(project_id=pid, usage_id=cast(int, u1.id), tag_id=tags["t1_1"].id),
        UsageTag(project_id=pid, usage_id=cast(int, u2.id), tag_id=tags["t1_2"].id),
    ])
    await db_session.commit()

    resp = await client.post(
        f"/projects/{pid}/chart",
        json={"name": "运输图", "sliceEntity": "USAGE"},
    )
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/tags",
        json={"tagIds": [tags["t1_1"].id, tags["t1_2"].id]},
    )
    assert resp.status_code == 200

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    slices = {s["name"]: s["value"] for s in resp.json()}
    assert slices == {"地下工程支护": 20.0, "主体工程支护": 30.0}


async def test_pie_data_task_mode(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    task: Task,
    usages,
):
    """TASK 模式：切片按任务标签聚合。"""
    pid = cast(int, project.id)
    db_session.add(
        TaskTag(project_id=pid, task_id=cast(int, task.id), tag_id=tags["t1_1"].id)
    )
    await db_session.commit()

    resp = await client.post(
        f"/projects/{pid}/chart",
        json={"name": "工序图", "sliceEntity": "TASK"},
    )
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/tags",
        json={"tagIds": [tags["t1_1"].id]},
    )
    assert resp.status_code == 200

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    # 任务名下全部实际用量：r1 20.0 + r2 30.0 + r3 20.0
    assert resp.json() == [{"name": "地下工程支护", "value": 70.0, "sortOrder": 0}]


async def test_pie_data_resource_categories_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resources: list[Resource],
    task: Task,
):
    """resourceCategories 过滤：transport 资源不计入 material 图。"""
    pid = cast(int, project.id)
    truck = Resource(
        project_id=pid,
        name="重型卡车",
        description="d",
        category=ResourceCategory.transport,
        carbon_factor=4.0,
    )
    db_session.add(truck)
    await db_session.commit()
    await db_session.refresh(truck)
    db_session.add(
        ResourceTag(
            project_id=pid,
            resource_id=cast(int, resources[0].id),
            tag_id=tags["t1_1"].id,
        )
    )
    db_session.add(
        ResourceTag(
            project_id=pid, resource_id=cast(int, truck.id), tag_id=tags["t1_1"].id
        )
    )
    db_session.add_all([
        TaskResourceUsage(
            project_id=pid,
            task_id=cast(int, task.id),
            resource_id=cast(int, resources[0].id),
            usage_date=date(2026, 1, 10),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=cast(int, task.id),
            resource_id=cast(int, truck.id),
            usage_date=date(2026, 1, 10),
            quantity=3.0,
            usage_type=UsageType.ACTUAL,
        ),
    ])
    await db_session.commit()

    resp = await client.post(
        f"/projects/{pid}/chart",
        json={"name": "用材图", "resourceCategories": ["material"]},
    )
    chart_id = resp.json()["id"]
    await client.put(
        f"/projects/{pid}/chart/{chart_id}/tags",
        json={"tagIds": [tags["t1_1"].id]},
    )

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    # 仅材料：10 * 2.0 = 20.0；卡车 3 * 4.0 = 12.0 被过滤
    assert resp.json() == [{"name": "地下工程支护", "value": 20.0, "sortOrder": 0}]


async def test_pie_data_any_mode(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resources: list[Resource],
    task: Task,
):
    """ANY 模式：任务标签与资源标签任一命中即计入切片。

    构造互斥校验允许的合法状态（每条用量只命中一个切片）：
    - r1 打资源标签 t1_1，用量挂在未打标任务 task2 下 → 计入 t1_1
    - task 打任务标签 t1_2，其名下 r2 用量 → 计入 t1_2
    - r2 打资源标签 t1_2，用量挂在未打标任务 task2 下 → 计入 t1_2
    """
    pid = cast(int, project.id)
    task2 = Task(project_id=pid, code="TC-002", name="任务2", duration=5.0)
    db_session.add(task2)
    await db_session.commit()
    await db_session.refresh(task2)
    r1, r2, _r3 = resources
    db_session.add(
        ResourceTag(
            project_id=pid, resource_id=cast(int, r1.id), tag_id=tags["t1_1"].id
        )
    )
    db_session.add(
        ResourceTag(
            project_id=pid, resource_id=cast(int, r2.id), tag_id=tags["t1_2"].id
        )
    )
    db_session.add(
        TaskTag(project_id=pid, task_id=cast(int, task.id), tag_id=tags["t1_2"].id)
    )
    db_session.add_all([
        TaskResourceUsage(
            project_id=pid,
            task_id=cast(int, task2.id),
            resource_id=cast(int, r1.id),
            usage_date=date(2026, 1, 10),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=cast(int, task2.id),
            resource_id=cast(int, r2.id),
            usage_date=date(2026, 1, 10),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=cast(int, task.id),
            resource_id=cast(int, r2.id),
            usage_date=date(2026, 1, 10),
            quantity=4.0,
            usage_type=UsageType.ACTUAL,
        ),
    ])
    await db_session.commit()

    resp = await client.post(
        f"/projects/{pid}/chart",
        json={"name": "ANY图", "sliceEntity": "ANY"},
    )
    chart_id = resp.json()["id"]
    await client.put(
        f"/projects/{pid}/chart/{chart_id}/tags",
        json={"tagIds": [tags["t1_1"].id, tags["t1_2"].id]},
    )

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    slices = {s["name"]: s["value"] for s in resp.json()}
    assert slices == {"地下工程支护": 20.0, "主体工程支护": 42.0}


async def test_set_chart_tags_reassign_overlap_ok(
    client: AsyncClient, project: Project, tags
):
    """图表替换式绑定重叠标签不 500（复合主键冲突回归）。"""
    pid = cast(int, project.id)
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "重叠图"})
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/tags",
        json={"tagIds": [tags["t1_1"].id]},
    )
    assert resp.status_code == 200
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/tags",
        json={"tagIds": [tags["t1_1"].id, tags["t1_2"].id]},
    )
    assert resp.status_code == 200
    assert [(t["tagId"], t["sortOrder"]) for t in resp.json()["tags"]] == [
        (tags["t1_1"].id, 0),
        (tags["t1_2"].id, 1),
    ]
