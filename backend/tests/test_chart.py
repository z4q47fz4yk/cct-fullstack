"""图表定义、切片配置与饼图数据 API 测试。

饼图口径：切片由标签组构成（同组=且，组间=或），命中基于 usage_snapshot
物化视图合并的标签名（含资源分类内置标签）。切片重叠 → 重复计入。
"""
# pyright: reportCallIssue=false

from datetime import date
from typing import TYPE_CHECKING, cast

import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.tag import ResourceTag, Tag
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
async def tags(db_session: AsyncSession, project: Project) -> dict[str, Tag]:
    """扁平标签（材料组 / 运输组）。"""
    pid = project.id
    assert pid is not None
    rows = [
        Tag(project_id=pid, name="施工用材", group="材料", description="d"),
        Tag(project_id=pid, name="地下工程支护", group="材料", description="d"),
        Tag(project_id=pid, name="主体工程支护", group="材料", description="d"),
        Tag(project_id=pid, name="施工运输", group="运输", description="d"),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    for t in rows:
        await db_session.refresh(t)
    return {"t1": rows[0], "t1_1": rows[1], "t1_2": rows[2], "t2": rows[3]}


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

    Jan r1 ACTUAL qty=10 → 20.0；Jan r2 ACTUAL qty=10 → 30.0
    Jan r3 ACTUAL qty=4  → 20.0；Feb r1 PLANNED qty=100 → 200.0
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
    db_session: AsyncSession, project: Project, tags, resources: list[Resource]
):
    """资源打标：r1→地下工程支护；r2→施工用材+主体工程支护；r3→施工运输。"""
    pid = project.id
    assert pid is not None
    db_session.add_all([
        ResourceTag(
            project_id=pid,
            resource_id=cast(int, resources[0].id),
            tag_id=tags["t1_1"].id,
        ),
        ResourceTag(
            project_id=pid, resource_id=cast(int, resources[1].id), tag_id=tags["t1"].id
        ),
        ResourceTag(
            project_id=pid,
            resource_id=cast(int, resources[1].id),
            tag_id=tags["t1_2"].id,
        ),
        ResourceTag(
            project_id=pid, resource_id=cast(int, resources[2].id), tag_id=tags["t2"].id
        ),
    ])
    await db_session.commit()


async def _snapshot_flush(client: AsyncClient, project_id: int) -> None:
    """通过手动刷新端点强制刷新（端点内 session 同事务可见未提交 fixture）。"""
    resp = await client.post(f"/projects/{project_id}/usage-snapshot/refresh")
    assert resp.status_code == 200


async def _create_chart(client, project_id: int, name: str, slices: list[dict]) -> int:
    resp = await client.post(f"/projects/{project_id}/chart", json={"name": name})
    assert resp.status_code == 201
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{project_id}/chart/{chart_id}/slices",
        json={"slices": slices},
    )
    assert resp.status_code == 200, resp.text
    return chart_id


# ============================================================
# 图表 CRUD / 切片配置
# ============================================================


async def test_create_chart(client: AsyncClient, project: Project):
    resp = await client.post(
        f"/projects/{project.id}/chart", json={"name": "施工用材各部分占比"}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "施工用材各部分占比"
    assert data["chartType"] == "PIE"
    assert data["slices"] == []


async def test_create_chart_duplicate_name_409(client: AsyncClient, project: Project):
    pid = project.id
    await client.post(f"/projects/{pid}/chart", json={"name": "图A"})
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图A"})
    assert resp.status_code == 409


async def test_set_slices(client: AsyncClient, project: Project, tags):
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图A"})
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/slices",
        json={
            "slices": [
                {
                    "name": "材料部分",
                    "tags": [{"tagId": tags["t1"].id, "group": 0}],
                }
            ]
        },
    )
    assert resp.status_code == 200
    slices = resp.json()["slices"]
    assert slices[0]["name"] == "材料部分"
    assert slices[0]["sortOrder"] == 0
    assert slices[0]["tags"][0]["tagName"] == "施工用材"
    assert slices[0]["tags"][0]["isBuiltin"] is False


async def test_set_slices_builtin_category(client: AsyncClient, project: Project):
    """切片可含内置分类标签（负 id）表达资源分类过滤。"""
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "材料图"})
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/slices",
        json={
            "slices": [
                {"name": "材料", "tags": [{"tagId": -3, "group": 0}]},  # 材料
                {"name": "运输", "tags": [{"tagId": -4, "group": 0}]},  # 运输
            ]
        },
    )
    assert resp.status_code == 200
    by_name = {s["name"]: s for s in resp.json()["slices"]}
    assert by_name["材料"]["tags"][0]["tagName"] == "材料"
    assert by_name["材料"]["tags"][0]["isBuiltin"] is True


async def test_set_slices_unknown_tag_422(client: AsyncClient, project: Project):
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图B"})
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/slices",
        json={"slices": [{"name": "x", "tags": [{"tagId": 999999}]}]},
    )
    assert resp.status_code == 422
    # 未知内置 id
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/slices",
        json={"slices": [{"name": "x", "tags": [{"tagId": -99}]}]},
    )
    assert resp.status_code == 422


async def test_set_slices_duplicate_name_422(client: AsyncClient, project: Project):
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图C"})
    chart_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/slices",
        json={
            "slices": [
                {"name": "A", "tags": [{"tagId": 1}]},
                {"name": "A", "tags": [{"tagId": 1}]},
            ]
        },
    )
    assert resp.status_code == 422


async def test_replace_slices_overwrite(client: AsyncClient, project: Project, tags):
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图D"})
    chart_id = resp.json()["id"]
    await client.put(
        f"/projects/{pid}/chart/{chart_id}/slices",
        json={"slices": [{"name": "旧", "tags": [{"tagId": tags["t1"].id}]}]},
    )
    resp = await client.put(
        f"/projects/{pid}/chart/{chart_id}/slices",
        json={
            "slices": [
                {"name": "新1", "tags": [{"tagId": tags["t1"].id, "group": 0}]},
                {"name": "新2", "tags": [{"tagId": tags["t2"].id, "group": 0}]},
            ]
        },
    )
    assert resp.status_code == 200
    assert [s["name"] for s in resp.json()["slices"]] == ["新1", "新2"]


async def test_get_chart_404(client: AsyncClient, project: Project):
    resp = await client.get(f"/projects/{project.id}/chart/999999")
    assert resp.status_code == 404


async def test_delete_chart(client: AsyncClient, project: Project, tags):
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "图E"})
    chart_id = resp.json()["id"]
    await client.put(
        f"/projects/{pid}/chart/{chart_id}/slices",
        json={"slices": [{"name": "A", "tags": [{"tagId": tags["t1"].id}]}]},
    )
    resp = await client.delete(f"/projects/{pid}/chart/{chart_id}")
    assert resp.status_code == 204
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}")
    assert resp.status_code == 404


# ============================================================
# 饼图数据
# ============================================================


async def test_pie_data_single_tag_slice(
    client: AsyncClient,
    project: Project,
    tags,
    usages,
    tag_links,
    db_session: AsyncSession,
):
    """切片绑定单个标签：命中其资源下用量。"""
    pid = cast(int, project.id)
    chart_id = await _create_chart(
        client,
        pid,
        "图1",
        [{"name": "地下工程支护", "tags": [{"tagId": tags["t1_1"].id}]}],
    )
    await _snapshot_flush(client, pid)

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    assert resp.json() == [{"name": "地下工程支护", "value": 20.0, "sortOrder": 0}]


async def test_pie_data_usage_type_planned(
    client: AsyncClient,
    project: Project,
    tags,
    usages,
    tag_links,
):
    pid = cast(int, project.id)
    chart_id = await _create_chart(
        client,
        pid,
        "计划图",
        [{"name": "地下工程支护", "tags": [{"tagId": tags["t1_1"].id}]}],
    )
    await _snapshot_flush(client, pid)

    resp = await client.get(
        f"/projects/{pid}/chart/{chart_id}/pie-data?usageType=PLANNED"
    )
    assert resp.json() == [{"name": "地下工程支护", "value": 200.0, "sortOrder": 0}]


async def test_pie_data_date_window(
    client: AsyncClient,
    project: Project,
    tags,
    usages,
    tag_links,
):
    pid = cast(int, project.id)
    chart_id = await _create_chart(
        client,
        pid,
        "日期图",
        [{"name": "地下工程支护", "tags": [{"tagId": tags["t1_1"].id}]}],
    )
    await _snapshot_flush(client, pid)

    resp = await client.get(
        f"/projects/{pid}/chart/{chart_id}/pie-data?startDate=2026-02-01"
    )
    assert resp.json() == [{"name": "地下工程支护", "value": 0.0, "sortOrder": 0}]


async def test_pie_data_builtin_category_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resources: list[Resource],
    task: Task,
):
    """内置分类切片（材料）只聚合该分类资源用量，过滤运输等其他分类。"""
    pid = project.id
    if TYPE_CHECKING:
        assert pid
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

    chart_id = await _create_chart(
        client,
        pid,
        "材料图",
        [{"name": "材料", "tags": [{"tagId": -3}]}],  # 内置材料
    )
    await _snapshot_flush(client, pid)

    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    # 仅材料资源 r1（cf=2.0）：10*2 = 20.0；卡车 12.0 不计数
    assert resp.json() == [{"name": "材料", "value": 20.0, "sortOrder": 0}]


async def test_pie_data_and_group_semantics(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resources: list[Resource],
    task: Task,
):
    """同组标签=且：资源须同时具备两个标签才命中切片。"""
    pid = project.id
    if TYPE_CHECKING:
        assert pid
    r1 = resources[0]
    # 打两个标签 (地下工程支护 + 施工用材) → 同组且命中
    db_session.add_all([
        ResourceTag(
            project_id=pid, resource_id=cast(int, r1.id), tag_id=tags["t1_1"].id
        ),
        ResourceTag(project_id=pid, resource_id=cast(int, r1.id), tag_id=tags["t1"].id),
    ])
    db_session.add(
        TaskResourceUsage(
            project_id=pid,
            task_id=cast(int, task.id),
            resource_id=cast(int, r1.id),
            usage_date=date(2026, 1, 10),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        )
    )
    await db_session.commit()

    # 且组：需 地下工程支护 AND 施工用材
    chart_id = await _create_chart(
        client,
        pid,
        "且图",
        [
            {
                "name": "支护+用材",
                "tags": [
                    {"tagId": tags["t1_1"].id, "group": 0},
                    {"tagId": tags["t1"].id, "group": 0},
                ],
            }
        ],
    )
    await _snapshot_flush(client, pid)
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.json() == [{"name": "支护+用材", "value": 20.0, "sortOrder": 0}]


async def test_pie_data_or_group_semantics(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resources: list[Resource],
    task: Task,
):
    """异组标签=或：命中任一即可。r1 只有施工用材标签 → 也命中。"""
    pid = project.id
    if TYPE_CHECKING:
        assert pid
    r1, r2 = resources[0], resources[1]
    db_session.add_all([
        ResourceTag(project_id=pid, resource_id=cast(int, r1.id), tag_id=tags["t1"].id),
        ResourceTag(project_id=pid, resource_id=cast(int, r2.id), tag_id=tags["t2"].id),
    ])
    db_session.add_all([
        TaskResourceUsage(
            project_id=pid,
            task_id=cast(int, task.id),
            resource_id=cast(int, r1.id),
            usage_date=date(2026, 1, 10),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        ),
        TaskResourceUsage(
            project_id=pid,
            task_id=cast(int, task.id),
            resource_id=cast(int, r2.id),
            usage_date=date(2026, 1, 10),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        ),
    ])
    await db_session.commit()

    chart_id = await _create_chart(
        client,
        pid,
        "或图",
        [
            {
                "name": "任一",
                "tags": [
                    {"tagId": tags["t1"].id, "group": 0},
                    {"tagId": tags["t2"].id, "group": 1},  # 或组
                ],
            }
        ],
    )
    await _snapshot_flush(client, pid)
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    # r1 2.0*10 + r2 3.0*10 = 50
    assert resp.json() == [{"name": "任一", "value": 50.0, "sortOrder": 0}]


async def test_pie_data_overlap_double_counts(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resources: list[Resource],
    task: Task,
):
    """切片重叠重复计入：r1 同时带两个标签且分别被两个切片命中。"""
    pid = project.id
    if TYPE_CHECKING:
        assert pid
    r1 = resources[0]
    db_session.add_all([
        ResourceTag(project_id=pid, resource_id=cast(int, r1.id), tag_id=tags["t1"].id),
        ResourceTag(
            project_id=pid, resource_id=cast(int, r1.id), tag_id=tags["t1_1"].id
        ),
    ])
    db_session.add(
        TaskResourceUsage(
            project_id=pid,
            task_id=cast(int, task.id),
            resource_id=cast(int, r1.id),
            usage_date=date(2026, 1, 10),
            quantity=10.0,
            usage_type=UsageType.ACTUAL,
        )
    )
    await db_session.commit()

    chart_id = await _create_chart(
        client,
        pid,
        "重叠图",
        [
            {"name": "施工用材", "tags": [{"tagId": tags["t1"].id}]},
            {"name": "地下工程支护", "tags": [{"tagId": tags["t1_1"].id}]},
        ],
    )
    await _snapshot_flush(client, pid)
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.status_code == 200
    # 同一用量命中两个切片：两边都计 20.0（重复计入）
    by_name = {s["name"]: s["value"] for s in resp.json()}
    assert by_name == {"施工用材": 20.0, "地下工程支护": 20.0}


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

    chart_id = await _create_chart(
        client,
        pid,
        "折减图",
        [{"name": "地下工程支护", "tags": [{"tagId": tags["t1_1"].id}]}],
    )
    await _snapshot_flush(client, pid)
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    # 因子 2.0/(2*1)=1.0 → 10*1.0=10.0
    assert resp.json() == [{"name": "地下工程支护", "value": 10.0, "sortOrder": 0}]


async def test_pie_data_empty_chart(client: AsyncClient, project: Project):
    pid = project.id
    resp = await client.post(f"/projects/{pid}/chart", json={"name": "空图"})
    chart_id = resp.json()["id"]
    resp = await client.get(f"/projects/{pid}/chart/{chart_id}/pie-data")
    assert resp.json() == []


async def test_pie_data_chart_404(client: AsyncClient, project: Project):
    resp = await client.get(f"/projects/{project.id}/chart/999999/pie-data")
    assert resp.status_code == 404
