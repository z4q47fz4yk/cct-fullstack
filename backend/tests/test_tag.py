"""标签（展平）与资源/任务/用量标签 API 测试。"""
# pyright: reportCallIssue=false

from typing import cast

import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel import select
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
    assert data["isDefault"] is False


async def test_list_tag_responses_include_is_default_flag(
    client: AsyncClient, project: Project, tags
):
    """所有 tag 响应（含默认与普通）都暴露 isDefault 字段。"""
    resp = await client.get(f"/projects/{project.id}/tag")
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert "isDefault" in item
        assert item["isDefault"] is False  # fixture 中均为普通标签


async def test_create_project_seeds_default_tags(
    client: AsyncClient, db_session: AsyncSession
):
    """通过 router 创建的项目自动拥有系统默认标签（is_default=true 且不可改/删）。"""
    resp = await client.post("/project", json={"name": "默认标签项目"})
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    list_resp = await client.get(f"/projects/{project_id}/tag")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    names = {it["name"] for it in items}
    assert names == {"人工", "机械", "材料", "运输", "其他"}
    assert all(it["isDefault"] is True for it in items)
    assert all(it["group"] == "资源类别" for it in items)


async def test_create_default_tags_isolated_per_project(client: AsyncClient):
    """两个项目各自的默认标签互不影响（id 空间与名称集合各自独立）。"""
    a = (await client.post("/project", json={"name": "项目A"})).json()
    b = (await client.post("/project", json={"name": "项目B"})).json()
    assert a["id"] != b["id"]

    list_a = (await client.get(f"/projects/{a['id']}/tag")).json()["items"]
    list_b = (await client.get(f"/projects/{b['id']}/tag")).json()["items"]
    ids_a = {it["id"] for it in list_a}
    ids_b = {it["id"] for it in list_b}
    assert ids_a.isdisjoint(ids_b)
    assert ids_a and ids_b


async def test_cannot_update_default_tag(client: AsyncClient):
    """默认标签不允许通过 PUT 修改：返回 422。"""
    pid = (await client.post("/project", json={"name": "保护-更新"})).json()["id"]
    items = (await client.get(f"/projects/{pid}/tag")).json()["items"]
    default_id = next(it["id"] for it in items if it["isDefault"])

    resp = await client.put(
        f"/projects/{pid}/tag/{default_id}",
        json={"name": "新名称", "group": "其他", "description": "改不动"},
    )
    assert resp.status_code == 422
    assert "默认标签" in resp.json()["detail"]


async def test_cannot_delete_default_tag(client: AsyncClient):
    """默认标签不允许通过 DELETE 删除：返回 422。"""
    pid = (await client.post("/project", json={"name": "保护-删除"})).json()["id"]
    items = (await client.get(f"/projects/{pid}/tag")).json()["items"]
    default_id = next(it["id"] for it in items if it["isDefault"])

    resp = await client.delete(f"/projects/{pid}/tag/{default_id}")
    assert resp.status_code == 422
    assert "默认标签" in resp.json()["detail"]

    # 标签仍存在
    again = await client.get(f"/projects/{pid}/tag/{default_id}")
    assert again.status_code == 200
    assert again.json()["isDefault"] is True


async def test_user_can_still_create_update_delete_normal_tags(
    client: AsyncClient,
):
    """默认标签保护不影响普通标签的 CRUD。"""
    pid = (await client.post("/project", json={"name": "普通标签"})).json()["id"]

    create_resp = await client.post(
        f"/projects/{pid}/tag",
        json={"name": "用户自定义", "group": "自定义分组"},
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["isDefault"] is False
    tag_id = create_resp.json()["id"]

    upd = await client.put(
        f"/projects/{pid}/tag/{tag_id}",
        json={"name": "用户自定义-改", "group": "自定义分组", "description": "d"},
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "用户自定义-改"

    delete = await client.delete(f"/projects/{pid}/tag/{tag_id}")
    assert delete.status_code == 204


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
    """项目分组统计：默认标签占一个「资源类别」分组，普通标签各自分组。"""
    resp = await client.get(f"/projects/{project.id}/tag/groups")
    assert resp.status_code == 200
    body = {g["group"]: g["count"] for g in resp.json()}
    # 项目级 fixture（Project 通过 ORM 直插）不会自动生成默认标签，
    # 所以本测试只用 fixture 写入的 3 条普通标签断言。
    assert body.get("材料") == 2
    assert body.get("运输") == 1
    assert sum(body.values()) == 3


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


async def test_delete_tag_removes_slice_mapping_by_fk(
    client: AsyncClient, db_session: AsyncSession, project: Project, tags
):
    """删除普通标签时 slice_tag_mapping 引用随 FK 级联清除（无残留映射）。"""
    from src.models.chart import ChartDefinition
    from src.models.slice import ChartSlice, SliceTagMapping

    pid = cast(int, project.id)
    chart = ChartDefinition(project_id=pid, name="FK图", description="d")
    db_session.add(chart)
    await db_session.commit()
    await db_session.refresh(chart)
    slice_obj = ChartSlice(project_id=pid, chart_id=cast(int, chart.id), name="S")
    db_session.add(slice_obj)
    await db_session.flush()
    db_session.add(
        SliceTagMapping(
            slice_id=cast(int, slice_obj.id), tag_id=cast(int, tags["t1"].id)
        )
    )
    await db_session.commit()

    resp = await client.delete(f"/projects/{pid}/tag/{tags['t1'].id}")
    assert resp.status_code == 204

    leftover = (
        await db_session.exec(
            select(SliceTagMapping).where(SliceTagMapping.tag_id == tags["t1"].id)
        )
    ).all()
    assert leftover == []


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


async def test_set_resource_tags_default_tag_422(
    client: AsyncClient,
    db_session: AsyncSession,
    project: Project,
    resource: Resource,
):
    """「资源类别」默认标签不允许手工打标（分类由资源类别自动命中）。"""
    pid = cast(int, project.id)
    # 默认标签行直接写入本测试项目（fixture 直插项目不自动生成）
    default_tag = Tag(
        project_id=pid,
        name="材料",
        group="资源类别",
        description="系统默认资源类别标签",
        is_default=True,
    )
    db_session.add(default_tag)
    await db_session.commit()
    await db_session.refresh(default_tag)
    assert default_tag.id is not None

    # 默认标签不可手工挂载
    resp = await client.put(
        f"/projects/{pid}/resource/{resource.id}/tags",
        json={"tagIds": [default_tag.id]},
    )
    assert resp.status_code == 422
    assert "默认分类标签" in resp.json()["detail"]

    # 负数 id（旧伪标签）不再有内置分类含义 → 直接按“不存在/不属于项目”拒绝
    resp = await client.put(
        f"/projects/{pid}/resource/{resource.id}/tags",
        json={"tagIds": [-3]},
    )
    assert resp.status_code == 422
    assert "不存在或不属于" in resp.json()["detail"]


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
