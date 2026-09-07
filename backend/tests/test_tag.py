"""标签（展平）与资源/任务/用量标签 API 测试。"""
# pyright: reportCallIssue=false

from typing import cast

import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project
from src.models.resource import Resource
from src.models.tag import ResourceTag, Tag
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
async def tags(db_session: AsyncSession, project: Project) -> dict[str, Tag]:
    """扁平标签：材料组（施工用材 / 水泥）+ 运输组（渣土运输）。"""
    pid = project.id
    assert pid is not None
    t1 = Tag(project_id=pid, name="施工用材", group="材料", description="d")
    t1_1 = Tag(project_id=pid, name="水泥", group="材料", description="d")
    t2 = Tag(project_id=pid, name="渣土运输", group="运输", description="d")
    db_session.add_all([t1, t1_1, t2])
    await db_session.commit()
    for t in (t1, t1_1, t2):
        await db_session.refresh(t)
    return {"t1": t1, "t1_1": t1_1, "t2": t2}


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


@pytest_asyncio.fixture
async def task(db_session: AsyncSession, project: Project) -> Task:
    pid = project.id
    assert pid is not None
    t = Task(project_id=pid, code="TAG-T1", name="T1", duration=5.0)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


# ============================================================
# 标签 CRUD（扁平）
# ============================================================


async def test_create_tag(client: AsyncClient, project: Project):
    resp = await client.post(
        f"/projects/{project.id}/tag",
        json={"name": "商品混凝土", "group": "材料", "description": "d"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "商品混凝土"
    assert data["group"] == "材料"
    assert data["id"] > 0


async def test_create_tag_default_group_empty(client: AsyncClient, project: Project):
    resp = await client.post(f"/projects/{project.id}/tag", json={"name": "未分组标签"})
    assert resp.status_code == 201
    assert resp.json()["group"] == ""


async def test_create_tag_duplicate_name_409(
    client: AsyncClient, project: Project, tags
):
    resp = await client.post(
        f"/projects/{project.id}/tag",
        json={"name": tags["t1"].name, "group": "其他"},
    )
    assert resp.status_code == 409


async def test_list_tags_group_filter(client: AsyncClient, project: Project, tags):
    resp = await client.get(f"/projects/{project.id}/tag?group=材料")
    assert resp.status_code == 200
    names = {it["name"] for it in resp.json()["items"]}
    assert names == {"施工用材", "水泥"}


async def test_list_tag_groups(client: AsyncClient, project: Project, tags):
    resp = await client.get(f"/projects/{project.id}/tag/groups")
    assert resp.status_code == 200
    body = {g["group"]: g["count"] for g in resp.json()}
    assert body == {"": 0, "材料": 2, "运输": 1}


async def test_get_tag_404(client: AsyncClient, project: Project):
    resp = await client.get(f"/projects/{project.id}/tag/999999")
    assert resp.status_code == 404


async def test_update_tag(client: AsyncClient, project: Project, tags):
    t = tags["t1"]
    resp = await client.put(
        f"/projects/{project.id}/tag/{t.id}",
        json={"group": "混凝土", "name": t.name},
    )
    assert resp.status_code == 200
    assert resp.json()["group"] == "混凝土"


async def test_update_tag_explicit_null_name_422(
    client: AsyncClient, project: Project, tags
):
    resp = await client.put(
        f"/projects/{project.id}/tag/{tags['t1'].id}",
        json={"name": None},
    )
    assert resp.status_code == 422


async def test_delete_tag(client: AsyncClient, project: Project, tags):
    t = tags["t1_1"]
    resp = await client.delete(f"/projects/{project.id}/tag/{t.id}")
    assert resp.status_code == 204
    resp = await client.get(f"/projects/{project.id}/tag/{t.id}")
    assert resp.status_code == 404


async def test_delete_builtin_tag_422(client: AsyncClient, project: Project):
    resp = await client.delete(f"/projects/{project.id}/tag/-3")
    assert resp.status_code == 422


# ============================================================
# 资源标签赋值
# ============================================================


async def test_set_and_get_resource_tags(
    client: AsyncClient, project: Project, tags, resource: Resource
):
    pid = project.id
    resp = await client.put(
        f"/projects/{pid}/resource/{resource.id}/tags",
        json={"tagIds": [tags["t1"].id, tags["t1_1"].id]},
    )
    assert resp.status_code == 200
    got = {it["id"] for it in resp.json()}
    assert got == {tags["t1"].id, tags["t1_1"].id}

    resp = await client.get(f"/projects/{pid}/resource/{resource.id}/tags")
    assert {it["id"] for it in resp.json()} == got


async def test_set_resource_tags_clears(
    client: AsyncClient, project: Project, tags, resource: Resource
):
    pid = project.id
    await client.put(
        f"/projects/{pid}/resource/{resource.id}/tags",
        json={"tagIds": [tags["t1"].id]},
    )
    resp = await client.put(
        f"/projects/{pid}/resource/{resource.id}/tags", json={"tagIds": []}
    )
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


async def test_set_resource_tags_builtin_neg_422(
    client: AsyncClient, project: Project, resource: Resource
):
    """内置分类标签（负 id）不允许手工打标。"""
    resp = await client.put(
        f"/projects/{project.id}/resource/{resource.id}/tags",
        json={"tagIds": [-3]},  # 材料
    )
    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert "内置分类" in body


async def test_set_resource_tags_resource_404(
    client: AsyncClient, project: Project, tags
):
    resp = await client.put(
        f"/projects/{project.id}/resource/999999/tags",
        json={"tagIds": []},
    )
    assert resp.status_code == 404


async def test_set_and_get_task_tags(
    client: AsyncClient, project: Project, tags, task: Task
):
    pid = project.id
    resp = await client.put(
        f"/projects/{pid}/task/{task.id}/tags",
        json={"tagIds": [tags["t1"].id, tags["t1_1"].id]},
    )
    assert resp.status_code == 200
    assert {it["id"] for it in resp.json()} == {tags["t1"].id, tags["t1_1"].id}
    resp = await client.get(f"/projects/{pid}/task/{task.id}/tags")
    assert {it["id"] for it in resp.json()} == {tags["t1"].id, tags["t1_1"].id}


async def test_set_task_tags_task_404(client: AsyncClient, project: Project, tags):
    resp = await client.put(
        f"/projects/{project.id}/task/999999/tags",
        json={"tagIds": [tags["t1"].id]},
    )
    assert resp.status_code == 404


# ============================================================
# 打标不再做图表互斥校验（重叠允许）
# ============================================================


async def test_resource_tags_allow_non_exclusive_overlap(
    client: AsyncClient,
    project: Project,
    tags,
    resource: Resource,
):
    """打标端点不再因标签跨图表互斥而 409：同一资源可挂任意标签组合。"""
    resp = await client.put(
        f"/projects/{project.id}/resource/{resource.id}/tags",
        json={"tagIds": [tags["t1"].id, tags["t2"].id]},
    )
    assert resp.status_code == 200


# ============================================================
# 标签下资源列表
# ============================================================


async def _link_resource_tags(
    db_session: AsyncSession, project: Project, links: list[tuple[int, int]]
) -> None:
    pid = project.id
    assert pid is not None
    db_session.add_all([
        ResourceTag(project_id=pid, resource_id=rid, tag_id=tid) for rid, tid in links
    ])
    await db_session.commit()


async def test_get_tag_resources_direct_only(
    client: AsyncClient, db_session: AsyncSession, project: Project, tags
):
    r1 = Resource(
        project_id=cast(int, project.id),
        name="R1",
        description="d",
        category=ResourceCategory.material,
    )
    r2 = Resource(
        project_id=cast(int, project.id),
        name="R2",
        description="d",
        category=ResourceCategory.material,
    )
    db_session.add_all([r1, r2])
    await db_session.commit()
    await db_session.refresh(r1)
    await db_session.refresh(r2)
    await _link_resource_tags(
        db_session,
        project,
        [
            (cast(int, r1.id), cast(int, tags["t1"].id)),
            (cast(int, r2.id), cast(int, tags["t1"].id)),
        ],
    )
    resp = await client.get(f"/projects/{project.id}/tag/{tags['t1'].id}/resources")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_get_tag_resources_tag_404(client: AsyncClient, project: Project):
    resp = await client.get(f"/projects/{project.id}/tag/999999/resources")
    assert resp.status_code == 404
