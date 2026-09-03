"""标签与资源标签 API 测试。"""
# pyright: reportCallIssue=false

from datetime import date
from typing import cast

import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.chart import ChartDefinition, ChartTagMapping
from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.tag import ResourceTag, Tag, TagDimension
from src.models.task import Task
from src.schemas.resource import ResourceCategory


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    """测试项目（CurrentProject 依赖需要）。"""
    p = Project(name="Tag Test Project", is_active=True)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def dimension(db_session: AsyncSession, project: Project) -> TagDimension:
    """默认标签维度。"""
    d = TagDimension(project_id=cast(int, project.id), name="默认维度", description="d")
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    return d


@pytest_asyncio.fixture
async def tags(
    db_session: AsyncSession, project: Project, dimension: TagDimension
) -> dict[str, Tag]:
    """标签树：施工用材(根) → 地下工程支护 / 主体工程支护；施工运输(根)。"""
    pid = project.id
    did = dimension.id
    assert pid is not None and did is not None
    t1 = Tag(project_id=pid, dimension_id=did, name="施工用材", description="d")
    db_session.add(t1)
    await db_session.commit()
    await db_session.refresh(t1)

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
    t2 = Tag(project_id=pid, dimension_id=did, name="施工运输", description="d")
    db_session.add_all([t1_1, t1_2, t2])
    await db_session.commit()
    for t in (t1_1, t1_2, t2):
        await db_session.refresh(t)
    return {"t1": t1, "t1_1": t1_1, "t1_2": t1_2, "t2": t2}


@pytest_asyncio.fixture
async def resource(db_session: AsyncSession, project: Project) -> Resource:
    pid = project.id
    assert pid is not None
    r = Resource(
        project_id=pid,
        name="R1-Material",
        description="d",
        category=ResourceCategory.material,
        carbon_factor=2.0,
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


# ============================================================
# 标签维度 CRUD
# ============================================================


async def test_create_tag_dimension(client: AsyncClient, project: Project):
    resp = await client.post(
        f"/projects/{project.id}/tag-dimension", json={"name": "工序维度"}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "工序维度"
    assert data["description"] == ""


async def test_create_tag_dimension_duplicate_409(
    client: AsyncClient, project: Project, dimension: TagDimension
):
    resp = await client.post(
        f"/projects/{project.id}/tag-dimension", json={"name": dimension.name}
    )
    assert resp.status_code == 409


async def test_list_tag_dimensions(
    client: AsyncClient, project: Project, dimension: TagDimension
):
    resp = await client.get(f"/projects/{project.id}/tag-dimension")
    assert resp.status_code == 200
    names = {it["name"] for it in resp.json()["items"]}
    assert dimension.name in names


async def test_update_tag_dimension(client: AsyncClient, project: Project, dimension):
    resp = await client.put(
        f"/projects/{project.id}/tag-dimension/{dimension.id}",
        json={"name": "改名维度"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名维度"


async def test_delete_tag_dimension_with_tags_409(
    client: AsyncClient, project: Project, tags
):
    resp = await client.delete(
        f"/projects/{project.id}/tag-dimension/{tags['t1'].dimension_id}"
    )
    assert resp.status_code == 409


async def test_delete_tag_dimension(
    client: AsyncClient, project: Project, dimension: TagDimension
):
    resp = await client.delete(f"/projects/{project.id}/tag-dimension/{dimension.id}")
    assert resp.status_code == 204


# ============================================================
# 标签 CRUD
# ============================================================


async def test_create_tag(client: AsyncClient, project: Project, dimension):
    resp = await client.post(
        f"/projects/{project.id}/tag",
        json={"name": "新建标签", "dimensionId": dimension.id},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "新建标签"
    assert data["parentId"] is None
    assert data["dimensionId"] == dimension.id
    assert data["description"] == ""
    assert data["id"] is not None


async def test_create_tag_missing_dimension_422(client: AsyncClient, project: Project):
    resp = await client.post(f"/projects/{project.id}/tag", json={"name": "无维度标签"})
    assert resp.status_code == 422


async def test_create_tag_with_parent(
    client: AsyncClient, project: Project, tags, dimension
):
    pid = project.id
    resp = await client.post(
        f"/projects/{pid}/tag",
        json={
            "name": "子标签",
            "dimensionId": dimension.id,
            "parentId": tags["t1"].id,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["parentId"] == tags["t1"].id


async def test_create_tag_cross_dimension_parent_422(
    client: AsyncClient, project: Project, tags
):
    """父标签与子标签不同维度 → 422。"""
    pid = project.id
    resp = await client.post(
        f"/projects/{pid}/tag-dimension", json={"name": "另一维度"}
    )
    other_dim = resp.json()["id"]
    resp = await client.post(
        f"/projects/{pid}/tag",
        json={
            "name": "跨维度子标签",
            "dimensionId": other_dim,
            "parentId": tags["t1"].id,
        },
    )
    assert resp.status_code == 422


async def test_same_name_across_dimensions_ok(
    client: AsyncClient, project: Project, tags
):
    """同一名称在不同维度可共存。"""
    pid = project.id
    resp = await client.post(
        f"/projects/{pid}/tag-dimension", json={"name": "位置维度"}
    )
    other_dim = resp.json()["id"]
    resp = await client.post(
        f"/projects/{pid}/tag",
        json={"name": "施工用材", "dimensionId": other_dim},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "施工用材"


async def test_create_tag_duplicate_name_409(
    client: AsyncClient, project: Project, tags
):
    resp = await client.post(
        f"/projects/{project.id}/tag",
        json={"name": "施工用材", "dimensionId": tags["t1"].dimension_id},
    )
    assert resp.status_code == 409


async def test_create_tag_parent_not_in_project_422(
    client: AsyncClient, project: Project, dimension
):
    resp = await client.post(
        f"/projects/{project.id}/tag",
        json={"name": "x", "dimensionId": dimension.id, "parentId": 999999},
    )
    assert resp.status_code == 422


async def test_list_tags(client: AsyncClient, project: Project, tags):
    resp = await client.get(f"/projects/{project.id}/tag")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 4
    names = {it["name"] for it in body["items"]}
    assert {"施工用材", "地下工程支护", "施工运输"} <= names


async def test_list_tags_name_filter(client: AsyncClient, project: Project, tags):
    resp = await client.get(f"/projects/{project.id}/tag?name=支护")
    assert resp.status_code == 200
    names = {it["name"] for it in resp.json()["items"]}
    assert names == {"地下工程支护", "主体工程支护"}


async def test_get_tag(client: AsyncClient, project: Project, tags):
    t = tags["t1_1"]
    resp = await client.get(f"/projects/{project.id}/tag/{t.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "地下工程支护"
    assert data["parentId"] == tags["t1"].id


async def test_get_tag_404(client: AsyncClient, project: Project):
    resp = await client.get(f"/projects/{project.id}/tag/999999")
    assert resp.status_code == 404


async def test_tag_tree(client: AsyncClient, project: Project, tags):
    resp = await client.get(f"/projects/{project.id}/tag/tree")
    assert resp.status_code == 200
    roots = {n["name"]: n for n in resp.json()}
    assert set(roots) == {"施工用材", "施工运输"}
    children = {c["name"] for c in roots["施工用材"]["children"]}
    assert children == {"地下工程支护", "主体工程支护"}


async def test_tag_tree_filter_by_dimension(
    client: AsyncClient, project: Project, tags
):
    """tree 按维度过滤：另一维度只有自身树。"""
    pid = project.id
    resp = await client.post(
        f"/projects/{pid}/tag-dimension", json={"name": "位置维度"}
    )
    other_dim = resp.json()["id"]
    await client.post(
        f"/projects/{pid}/tag",
        json={"name": "生活区", "dimensionId": other_dim},
    )
    resp = await client.get(
        f"/projects/{pid}/tag/tree?dimensionId={tags['t1'].dimension_id}"
    )
    roots = {n["name"]: n for n in resp.json()}
    assert set(roots) == {"施工用材", "施工运输"}
    resp = await client.get(f"/projects/{pid}/tag/tree?dimensionId={other_dim}")
    roots = {n["name"]: n for n in resp.json()}
    assert set(roots) == {"生活区"}


async def test_update_tag_move_to_root(client: AsyncClient, project: Project, tags):
    t = tags["t1_1"]
    resp = await client.put(
        f"/projects/{project.id}/tag/{t.id}",
        json={"name": "改名的支护", "parentId": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "改名的支护"
    assert data["parentId"] is None


async def test_update_tag_move_to_other_dimension(
    client: AsyncClient, project: Project, tags
):
    """dimensionId 变更后，子孙标签随同迁移。"""
    pid = project.id
    resp = await client.post(f"/projects/{pid}/tag-dimension", json={"name": "新维度"})
    other_dim = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/tag/{tags['t1'].id}",
        json={"dimensionId": other_dim},
    )
    assert resp.status_code == 200
    assert resp.json()["dimensionId"] == other_dim
    resp = await client.get(f"/projects/{pid}/tag/{tags['t1_1'].id}")
    assert resp.json()["dimensionId"] == other_dim


async def test_update_tag_dimension_non_root_422(
    client: AsyncClient, project: Project, tags
):
    """非根标签仅换维度（父级留在旧维度）→ 422，防止标签树跨维度。"""
    pid = project.id
    resp = await client.post(
        f"/projects/{pid}/tag-dimension", json={"name": "另一维度"}
    )
    other_dim = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/tag/{tags['t1_1'].id}",
        json={"dimensionId": other_dim},
    )
    assert resp.status_code == 422
    assert "parentId" in resp.json()["detail"]
    # 未发生迁移：标签仍留在原维度
    resp = await client.get(f"/projects/{pid}/tag/{tags['t1_1'].id}")
    assert resp.json()["dimensionId"] == tags["t1_1"].dimension_id
    resp = await client.get(f"/projects/{pid}/tag/{tags['t1'].id}")
    assert resp.json()["dimensionId"] == tags["t1"].dimension_id


async def test_update_tag_dimension_to_root_then_ok(
    client: AsyncClient, project: Project, tags
):
    """非根标签换维度 + parentId 显式 null（随迁成新维度顶级）→ 200。"""
    pid = project.id
    resp = await client.post(
        f"/projects/{pid}/tag-dimension", json={"name": "另一维度"}
    )
    other_dim = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/tag/{tags['t1_1'].id}",
        json={"dimensionId": other_dim, "parentId": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dimensionId"] == other_dim
    assert data["parentId"] is None
    # 原父级仍在原维度，且不再包含该子标签
    resp = await client.get(f"/projects/{pid}/tag/{tags['t1'].id}")
    assert resp.json()["dimensionId"] == tags["t1"].dimension_id


async def test_update_tag_dimension_with_new_parent_ok(
    client: AsyncClient, project: Project, tags
):
    """非根标签换维度 + 指定新维度下的父级 → 200，父子维度一致。"""
    pid = project.id
    resp = await client.post(
        f"/projects/{pid}/tag-dimension", json={"name": "另一维度"}
    )
    other_dim = resp.json()["id"]
    resp = await client.post(
        f"/projects/{pid}/tag",
        json={"name": "新维度根", "dimensionId": other_dim},
    )
    new_root_id = resp.json()["id"]
    resp = await client.put(
        f"/projects/{pid}/tag/{tags['t1_1'].id}",
        json={"dimensionId": other_dim, "parentId": new_root_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dimensionId"] == other_dim
    assert data["parentId"] == new_root_id


async def test_update_tag_self_parent_422(client: AsyncClient, project: Project, tags):
    t = tags["t1"]
    resp = await client.put(
        f"/projects/{project.id}/tag/{t.id}", json={"parentId": t.id}
    )
    assert resp.status_code == 422


async def test_update_tag_cycle_422(client: AsyncClient, project: Project, tags):
    """把根标签移动到自己的子孙之下 → 422。"""
    t1, t1_1 = tags["t1"], tags["t1_1"]
    resp = await client.put(
        f"/projects/{project.id}/tag/{t1.id}",
        json={"parentId": t1_1.id},
    )
    assert resp.status_code == 422


async def test_update_tag_explicit_null_name_422(
    client: AsyncClient, project: Project, tags
):
    resp = await client.put(
        f"/projects/{project.id}/tag/{tags['t1'].id}",
        json={"name": None},
    )
    assert resp.status_code == 422


async def test_delete_tag_with_children_409(
    client: AsyncClient, project: Project, tags
):
    resp = await client.delete(f"/projects/{project.id}/tag/{tags['t1'].id}")
    assert resp.status_code == 409


async def test_delete_tag(client: AsyncClient, project: Project, tags):
    t = tags["t1_2"]
    resp = await client.delete(f"/projects/{project.id}/tag/{t.id}")
    assert resp.status_code == 204
    resp = await client.get(f"/projects/{project.id}/tag/{t.id}")
    assert resp.status_code == 404


# ============================================================
# 资源标签赋值
# ============================================================


async def test_set_and_get_resource_tags(
    client: AsyncClient, project: Project, tags, resource: Resource
):
    pid, rid = project.id, resource.id
    resp = await client.put(
        f"/projects/{pid}/resource/{rid}/tags",
        json={"tagIds": [tags["t1"].id, tags["t1_1"].id]},
    )
    assert resp.status_code == 200
    expected = {tags["t1"].id, tags["t1_1"].id}
    assert {it["id"] for it in resp.json()} == expected

    resp = await client.get(f"/projects/{pid}/resource/{rid}/tags")
    assert resp.status_code == 200
    assert {it["id"] for it in resp.json()} == expected


async def test_set_resource_tags_clears(
    client: AsyncClient, project: Project, tags, resource: Resource
):
    pid, rid = project.id, resource.id
    await client.put(
        f"/projects/{pid}/resource/{rid}/tags", json={"tagIds": [tags["t1"].id]}
    )
    resp = await client.put(f"/projects/{pid}/resource/{rid}/tags", json={"tagIds": []})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_set_resource_tags_not_in_project_422(
    client: AsyncClient, project: Project, tags, resource: Resource
):
    resp = await client.put(
        f"/projects/{project.id}/resource/{resource.id}/tags",
        json={"tagIds": [tags["t1"].id, 999999]},
    )
    assert resp.status_code == 422


async def test_set_resource_tags_resource_404(
    client: AsyncClient, project: Project, tags
):
    resp = await client.put(
        f"/projects/{project.id}/resource/999999/tags",
        json={"tagIds": []},
    )
    assert resp.status_code == 404


async def test_chart_conflict_409(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resource: Resource,
):
    """方案A：图表同时绑定两个标签时，资源被打上这两个标签 → 409。"""
    pid = cast(int, project.id)
    chart = ChartDefinition(
        project_id=pid, name="冲突图", description="d", chart_type="PIE"
    )
    db_session.add(chart)
    await db_session.commit()
    await db_session.refresh(chart)
    chart_id = cast(int, chart.id)
    db_session.add_all([
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1_1"].id, sort_order=0
        ),
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1_2"].id, sort_order=1
        ),
    ])
    await db_session.commit()

    resp = await client.put(
        f"/projects/{pid}/resource/{resource.id}/tags",
        json={"tagIds": [tags["t1_1"].id, tags["t1_2"].id]},
    )
    assert resp.status_code == 409


async def test_chart_conflict_passes_when_not_in_same_chart(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resource: Resource,
):
    """两个标签分属两个不同图表 → 不冲突，赋值成功。"""
    pid = cast(int, project.id)
    for i, tag_key in enumerate(("t1_1", "t1_2")):
        chart = ChartDefinition(
            project_id=pid, name=f"图{i}", description="d", chart_type="PIE"
        )
        db_session.add(chart)
        await db_session.commit()
        await db_session.refresh(chart)
        chart_id = cast(int, chart.id)
        db_session.add(
            ChartTagMapping(
                project_id=pid, chart_id=chart_id, tag_id=tags[tag_key].id, sort_order=0
            )
        )
    await db_session.commit()

    resp = await client.put(
        f"/projects/{pid}/resource/{resource.id}/tags",
        json={"tagIds": [tags["t1_1"].id, tags["t1_2"].id]},
    )
    assert resp.status_code == 200


# ============================================================
# 标签直接关联的资源
# ============================================================


@pytest_asyncio.fixture
async def resources(db_session: AsyncSession, project: Project) -> list[Resource]:
    """三个资源：r1/r2 直挂 t1，r3 仅挂 t1 的子标签 t1_1。"""
    pid = project.id
    assert pid is not None
    rs = [
        Resource(
            project_id=pid,
            name=f"R{i}",
            description="d",
            category=ResourceCategory.material,
            carbon_factor=1.0,
        )
        for i in range(3)
    ]
    db_session.add_all(rs)
    await db_session.commit()
    for r in rs:
        await db_session.refresh(r)
    return rs


async def _link_resource_tags(
    db_session: AsyncSession,
    project: Project,
    links: list[tuple[int, int]],
) -> None:
    pid = project.id
    assert pid is not None
    for rid, tid in links:
        db_session.add(ResourceTag(project_id=pid, resource_id=rid, tag_id=tid))
    await db_session.commit()


async def test_get_tag_resources_direct_only(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resources,
):
    """仅返回直接关联资源，不含子标签（t1 不含 r3）。"""
    pid = project.id
    r1, r2, r3 = resources
    await _link_resource_tags(
        db_session,
        project,
        [
            (r1.id, tags["t1"].id),
            (r2.id, tags["t1"].id),
            (r3.id, tags["t1_1"].id),  # 子标签，不计入 t1 直接资源
        ],
    )
    resp = await client.get(f"/projects/{pid}/tag/{tags['t1'].id}/resources")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert {it["id"] for it in data["items"]} == {r1.id, r2.id}


async def test_get_tag_resources_empty(client: AsyncClient, project: Project, tags):
    resp = await client.get(f"/projects/{project.id}/tag/{tags['t1'].id}/resources")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_get_tag_resources_pagination(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resources,
):
    pid = project.id
    r1, r2, r3 = resources
    await _link_resource_tags(
        db_session,
        project,
        [
            (r1.id, tags["t1"].id),
            (r2.id, tags["t1"].id),
            (r3.id, tags["t1"].id),
        ],
    )
    resp = await client.get(
        f"/projects/{pid}/tag/{tags['t1'].id}/resources?per_page=2&page=2"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == r3.id


async def test_get_tag_resources_tag_404(client: AsyncClient, project: Project):
    resp = await client.get(f"/projects/{project.id}/tag/999999/resources")
    assert resp.status_code == 404


# ============================================================
# 任务标签赋值
# ============================================================


@pytest_asyncio.fixture
async def task(db_session: AsyncSession, project: Project) -> Task:
    pid = project.id
    assert pid is not None
    t = Task(project_id=pid, code="TC-001", name="任务1", duration=5.0)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


async def test_set_and_get_task_tags(
    client: AsyncClient, project: Project, tags, task: Task
):
    pid, tid = project.id, task.id
    resp = await client.put(
        f"/projects/{pid}/task/{tid}/tags",
        json={"tagIds": [tags["t1"].id, tags["t1_1"].id]},
    )
    assert resp.status_code == 200
    assert {it["id"] for it in resp.json()} == {tags["t1"].id, tags["t1_1"].id}

    resp = await client.get(f"/projects/{pid}/task/{tid}/tags")
    assert resp.status_code == 200
    assert {it["id"] for it in resp.json()} == {tags["t1"].id, tags["t1_1"].id}


async def test_set_task_tags_clears(
    client: AsyncClient, project: Project, tags, task: Task
):
    pid, tid = project.id, task.id
    await client.put(
        f"/projects/{pid}/task/{tid}/tags", json={"tagIds": [tags["t1"].id]}
    )
    resp = await client.put(f"/projects/{pid}/task/{tid}/tags", json={"tagIds": []})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_set_task_tags_task_404(client: AsyncClient, project: Project, tags):
    resp = await client.put(
        f"/projects/{project.id}/task/999999/tags",
        json={"tagIds": [tags["t1"].id]},
    )
    assert resp.status_code == 404


async def test_set_task_tags_not_in_project_422(
    client: AsyncClient, project: Project, tags, task: Task
):
    resp = await client.put(
        f"/projects/{project.id}/task/{task.id}/tags",
        json={"tagIds": [tags["t1"].id, 999999]},
    )
    assert resp.status_code == 422


async def test_task_chart_conflict_409(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    task: Task,
):
    """任务被打上同一图表的两个切片标签 → 409。"""
    pid = cast(int, project.id)
    chart = ChartDefinition(
        project_id=pid,
        name="任务冲突图",
        description="d",
        chart_type="PIE",
        slice_entity="TASK",
    )
    db_session.add(chart)
    await db_session.commit()
    await db_session.refresh(chart)
    chart_id = cast(int, chart.id)
    db_session.add_all([
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1_1"].id, sort_order=0
        ),
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1_2"].id, sort_order=1
        ),
    ])
    await db_session.commit()

    resp = await client.put(
        f"/projects/{pid}/task/{task.id}/tags",
        json={"tagIds": [tags["t1_1"].id, tags["t1_2"].id]},
    )
    assert resp.status_code == 409


async def test_parent_child_both_slices_conflict_409(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resource: Resource,
):
    """图同时绑定父+子标签，资源只打子标签也会被子树展开双计 → 409。"""
    pid = cast(int, project.id)
    chart = ChartDefinition(
        project_id=pid, name="父子切片图", description="d", chart_type="PIE"
    )
    db_session.add(chart)
    await db_session.commit()
    await db_session.refresh(chart)
    chart_id = cast(int, chart.id)
    db_session.add_all([
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1"].id, sort_order=0
        ),
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1_1"].id, sort_order=1
        ),
    ])
    await db_session.commit()

    resp = await client.put(
        f"/projects/{pid}/resource/{resource.id}/tags",
        json={"tagIds": [tags["t1_1"].id]},
    )
    assert resp.status_code == 409


# ============================================================
# 用量标签赋值
# ============================================================


@pytest_asyncio.fixture
async def usage(
    db_session: AsyncSession,
    project: Project,
    task: Task,
    resource: Resource,
) -> TaskResourceUsage:
    pid = project.id
    assert pid is not None and task.id is not None and resource.id is not None
    u = TaskResourceUsage(
        project_id=pid,
        task_id=task.id,
        resource_id=resource.id,
        usage_date=date(2026, 1, 10),
        quantity=10.0,
        usage_type=UsageType.ACTUAL,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


async def test_set_and_get_usage_tags(
    client: AsyncClient, project: Project, tags, usage: TaskResourceUsage
):
    pid, uid = project.id, usage.id
    resp = await client.put(
        f"/projects/{pid}/resource-usage/{uid}/tags",
        json={"tagIds": [tags["t2"].id]},
    )
    assert resp.status_code == 200
    assert [it["id"] for it in resp.json()] == [tags["t2"].id]

    resp = await client.get(f"/projects/{pid}/resource-usage/{uid}/tags")
    assert resp.status_code == 200
    assert [it["id"] for it in resp.json()] == [tags["t2"].id]


async def test_set_usage_tags_usage_404(client: AsyncClient, project: Project, tags):
    resp = await client.put(
        f"/projects/{project.id}/resource-usage/999999/tags",
        json={"tagIds": [tags["t2"].id]},
    )
    assert resp.status_code == 404


async def test_usage_chart_conflict_409(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    usage: TaskResourceUsage,
):
    """USAGE 图表（sliceEntity=USAGE）：用量打上两个切片标签 → 409。"""
    pid = cast(int, project.id)
    chart = ChartDefinition(
        project_id=pid,
        name="用量冲突图",
        description="d",
        chart_type="PIE",
        slice_entity="USAGE",
    )
    db_session.add(chart)
    await db_session.commit()
    await db_session.refresh(chart)
    chart_id = cast(int, chart.id)
    db_session.add_all([
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1_1"].id, sort_order=0
        ),
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1_2"].id, sort_order=1
        ),
    ])
    await db_session.commit()

    resp = await client.put(
        f"/projects/{pid}/resource-usage/{usage.id}/tags",
        json={"tagIds": [tags["t1_1"].id, tags["t1_2"].id]},
    )
    assert resp.status_code == 409


async def test_any_chart_cross_entity_conflict_409(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    tags,
    resource: Resource,
    usage: TaskResourceUsage,
):
    """ANY 图表：资源打一个切片标签、其用量打另一个切片标签 → 409。"""
    pid = cast(int, project.id)
    chart = ChartDefinition(
        project_id=pid,
        name="ANY冲突图",
        description="d",
        chart_type="PIE",
        slice_entity="ANY",
    )
    db_session.add(chart)
    await db_session.commit()
    await db_session.refresh(chart)
    chart_id = cast(int, chart.id)
    db_session.add_all([
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1_1"].id, sort_order=0
        ),
        ChartTagMapping(
            project_id=pid, chart_id=chart_id, tag_id=tags["t1_2"].id, sort_order=1
        ),
    ])
    await db_session.commit()

    # 先给用量打 t1_2，再给资源打 t1_1 → 该用量的资源+用量标签跨两个切片
    resp = await client.put(
        f"/projects/{pid}/resource-usage/{usage.id}/tags",
        json={"tagIds": [tags["t1_2"].id]},
    )
    assert resp.status_code == 200
    resp = await client.put(
        f"/projects/{pid}/resource/{resource.id}/tags",
        json={"tagIds": [tags["t1_1"].id]},
    )
    assert resp.status_code == 409


async def test_set_resource_tags_reassign_overlap_ok(
    client: AsyncClient, project: Project, tags, resource: Resource
):
    """替换式重赋值：旧标签与新标签重叠时不应 500（INSERT 先于 DELETE 的回归）。"""
    pid, rid = project.id, resource.id
    resp = await client.put(
        f"/projects/{pid}/resource/{rid}/tags",
        json={"tagIds": [tags["t1"].id]},
    )
    assert resp.status_code == 200
    resp = await client.put(
        f"/projects/{pid}/resource/{rid}/tags",
        json={"tagIds": [tags["t1"].id, tags["t1_1"].id]},
    )
    assert resp.status_code == 200
    assert {it["id"] for it in resp.json()} == {tags["t1"].id, tags["t1_1"].id}


async def test_set_task_tags_reassign_overlap_ok(
    client: AsyncClient, project: Project, tags, task: Task
):
    """任务标签替换式重赋值重叠不 500。"""
    pid, tid = project.id, task.id
    await client.put(
        f"/projects/{pid}/task/{tid}/tags",
        json={"tagIds": [tags["t2"].id]},
    )
    resp = await client.put(
        f"/projects/{pid}/task/{tid}/tags",
        json={"tagIds": [tags["t2"].id, tags["t1_1"].id]},
    )
    assert resp.status_code == 200
    assert {it["id"] for it in resp.json()} == {tags["t2"].id, tags["t1_1"].id}


async def test_set_usage_tags_reassign_overlap_ok(
    client: AsyncClient, project: Project, tags, usage: TaskResourceUsage
):
    """用量标签替换式重赋值重叠不 500。"""
    pid, uid = project.id, usage.id
    await client.put(
        f"/projects/{pid}/resource-usage/{uid}/tags",
        json={"tagIds": [tags["t2"].id]},
    )
    resp = await client.put(
        f"/projects/{pid}/resource-usage/{uid}/tags",
        json={"tagIds": [tags["t2"].id, tags["t1_1"].id]},
    )
    assert resp.status_code == 200
    assert {it["id"] for it in resp.json()} == {tags["t2"].id, tags["t1_1"].id}
