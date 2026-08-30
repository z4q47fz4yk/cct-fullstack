"""ResourcePublic（共享资源字典）测试。

公共表是只读字典，迁移时会从 ``alembic/data/resource_db.csv`` 回填种子；
测试库 CCTv2-test 已包含 831 条种子（以 SharedSeedTotal 等几个常量靠
``GET /public-resource?per_page=1000`` 拿全量 base 计算）。
"""
# pyright: reportCallIssue=false

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.resource_public import ResourcePublic
from src.schemas.resource import ResourceCategory

# 默认项目 id（由 alembic 迁移 10f6fdbf450e seed）
PID = 1

# /public-resource 不需要 project 上下文
DICT_PATH = "/public-resource"
COPY_PATH = f"/projects/{PID}/public-resource/batch-copy"


@pytest_asyncio.fixture
async def public_resources(db_session: AsyncSession):
    """插入 5 条与种子互不重名的公共资源，用于本测试套件。"""

    # 使用 fixture 唯一性前缀避免与 csv seed 800+ 条撞名
    rp = [
        ResourcePublic(
            id=9000 + i,
            name=f"ztpub-{i + 1}",
            description=f"共享 fixture {i + 1}",
            category=category,
            unit="kg",
            unit_price=1.0 + i,
            carbon_factor=0.1 * i,
        )
        for i, category in enumerate([
            ResourceCategory.labor,
            ResourceCategory.labor,
            ResourceCategory.machinery,
            ResourceCategory.material,
            ResourceCategory.transport,
        ])
    ]
    db_session.add_all(rp)
    await db_session.commit()
    for r in rp:
        await db_session.refresh(r)
    return rp


async def _seed_total(client: AsyncClient) -> int:
    resp = await client.get(f"{DICT_PATH}?per_page=1000")
    assert resp.status_code == 200
    return resp.json()["total"]


async def _seed_items(client: AsyncClient) -> list[dict]:
    resp = await client.get(f"{DICT_PATH}?per_page=1000")
    assert resp.status_code == 200
    return resp.json()["items"]


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("", id="all"),
        pytest.param("page=1", id="pagination1"),
        pytest.param("page=2&per_page=2", id="pagination2"),
        pytest.param("category=labor", id="filter_by_category"),
        pytest.param("name=ztpub", id="filter_by_name"),
    ],
)
async def test_list_public_resources(public_resources, client: AsyncClient, query: str):
    """GET /public-resource 分页/筛选。"""

    base_total = await _seed_total(client)
    base_items = await _seed_items(client)

    expected_items = [it for it in base_items if it["name"].startswith("ztpub-")]
    # 重新加上本测试可能没刷新的 fixture 项
    seen = {it["id"] for it in expected_items}
    for r in public_resources:
        if r.id not in seen:
            expected_items.append({
                "id": r.id,
                "name": r.name,
                "category": r.category.value,
            })

    resp = await client.get(f"{DICT_PATH}?{query}")
    assert resp.status_code == 200
    data = resp.json()

    if query == "":
        assert data["total"] == base_total
        assert len(data["items"]) == min(10, base_total)
        return

    if query == "page=1":
        assert data["total"] == base_total
        return

    if query.startswith("page=2"):
        # 本身只关心 total 字段存在
        assert "total" in data
        return

    if query == "category=labor":
        # 至少包含我们的 2 条 ztpub labor 项
        ztpub_labor = [it for it in data["items"] if it["name"].startswith("ztpub-")]
        assert len(ztpub_labor) == 2
        assert all(it["category"] == "labor" for it in data["items"])
        return

    if query == "name=ztpub":
        ztpub_items = [it for it in data["items"] if it["name"].startswith("ztpub-")]
        assert len(ztpub_items) == 5
        return


async def test_get_public_resource(public_resources, client: AsyncClient):
    """GET /public-resource/{id} 拿详情；不存在 404。"""

    r = public_resources[0]
    resp = await client.get(f"{DICT_PATH}/{r.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == r.id
    assert data["name"] == r.name
    assert data["category"] == r.category.value

    resp404 = await client.get(f"{DICT_PATH}/99999999")
    assert resp404.status_code == 404


async def test_no_crud_endpoints_on_public_resource(client: AsyncClient):
    """只读约束：/public-resource 与 /public-resource/{id} 上 POST/PUT/DELETE 不应存在。

    任何写入应返回 405（方法不允许）。
    """

    # 字典列表路径不应允许写入
    for verb in ("post", "put", "delete", "patch"):
        method = getattr(client, verb)
        resp = await method(DICT_PATH)
        assert resp.status_code == 405, (verb, resp.status_code, resp.text)

    # 字典详情路径也不应允许写入
    for verb in ("post", "put", "delete", "patch"):
        method = getattr(client, verb)
        resp = await method(f"{DICT_PATH}/1")
        assert resp.status_code == 405, (verb, resp.status_code, resp.text)


async def test_copy_to_project__by_ids_all_copied(
    public_resources, client: AsyncClient
):
    """ids 命中全部 fixture 资源 → 全部 copied。"""

    ids = [r.id for r in public_resources]
    resp = await client.post(COPY_PATH, json={"ids": ids})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["projectId"] == PID
    assert data["totalRequested"] == len(ids)
    assert len(data["copied"]) == len(ids)
    assert len(data["skipped"]) == 0
    assert len(data["notFound"]) == 0

    for item in data["copied"]:
        assert item["status"] == "copied"
        assert item["targetId"] is not None

    # 验证目标项目里能看到这些资源
    listed = await client.get(f"/projects/{PID}/resource?per_page=1000")
    listed_items = listed.json()["items"]
    names_in_project = {it["name"] for it in listed_items}
    for r in public_resources:
        assert r.name in names_in_project


async def test_copy_to_project__name_clash(public_resources, client: AsyncClient):
    """先在目标项目种 1 条与 fixture 同名资源 → 该条进 skipped。"""

    # 在目标项目里先插入一条与 fixture[0] 同名的 Resource（通过 endpoint 创建）
    await client.get(f"{DICT_PATH}/{public_resources[0].id}")  # trigger ready session
    # 用 endpoint 也行：用项目内的创建 endpoint
    create_resp = await client.post(
        f"/projects/{PID}/resource",
        json={
            "name": public_resources[0].name,
            "description": "已存在冲突",
            "category": "labor",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created_id = create_resp.json()["id"]

    ids = [r.id for r in public_resources]
    resp = await client.post(COPY_PATH, json={"ids": ids})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(data["copied"]) == len(ids) - 1
    assert len(data["skipped"]) == 1
    skipped = data["skipped"][0]
    assert skipped["id"] == public_resources[0].id
    assert skipped["status"] == "skipped"
    assert skipped["reason"] and "已存在" in skipped["reason"]

    # 跳过的条目在目标项目里仍是先前创建的那一条，没被覆盖
    listed = await client.get(f"/projects/{PID}/resource?per_page=1000")
    matched = [
        it for it in listed.json()["items"] if it["name"] == public_resources[0].name
    ]
    assert len(matched) == 1
    assert matched[0]["id"] == created_id


async def test_copy_to_project__by_ids_with_unknown(
    public_resources, client: AsyncClient
):
    """ids 中混入不存在的 id → not_found 分段。"""

    real_ids = [r.id for r in public_resources[:2]]
    fake_id = 99999999
    resp = await client.post(COPY_PATH, json={"ids": real_ids + [fake_id]})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(data["copied"]) == len(real_ids)
    assert len(data["notFound"]) == 1
    assert data["notFound"][0]["id"] == fake_id
    assert data["notFound"][0]["status"] == "not_found"


async def test_copy_to_project__by_category(public_resources, client: AsyncClient):
    """category 单独存在 → 拷该分类全部。fixture 中 labor 有 2 条。"""

    resp = await client.post(COPY_PATH, json={"category": "labor"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # 至少有 fixture 的 2 条 labor；csv seed 中也有 labor 可能也被拷进来（取决于 seed）
    copied_ids = {it["id"] for it in data["copied"]}
    assert public_resources[0].id in copied_ids
    assert public_resources[1].id in copied_ids
    # 非 labor 不在 copied
    assert public_resources[2].id not in copied_ids


async def test_copy_to_project__empty_request_422(client: AsyncClient):
    """既不提供 ids 也不提供 category → 422。"""

    resp = await client.post(COPY_PATH, json={})
    assert resp.status_code == 422
    detail = str(resp.json())
    assert "必须提供" in detail


async def test_copy_to_project__ids_and_category_exclusive_422(client: AsyncClient):
    """ids 与 category 同时给 → 422（schema validator）。"""

    resp = await client.post(COPY_PATH, json={"ids": [1, 2], "category": "labor"})
    assert resp.status_code == 422
    detail = str(resp.json())
    assert "互斥" in detail


async def test_copy_to_project__project_not_found_404(client: AsyncClient):
    """URL 中 project_id 不存在 → 404（来自 CurrentProject 依赖）。"""

    resp = await client.post(
        "/projects/999999/public-resource/batch-copy",
        json={"ids": [1, 2, 3]},
    )
    assert resp.status_code == 404


async def test_copy_idempotent(public_resources, client: AsyncClient):
    """同一个 ids 拷贝两次：第二次全部 skipped。"""

    ids = [r.id for r in public_resources]

    first = await client.post(COPY_PATH, json={"ids": ids})
    assert first.status_code == 200
    assert len(first.json()["copied"]) == len(ids)
    assert len(first.json()["skipped"]) == 0

    second = await client.post(COPY_PATH, json={"ids": ids})
    assert second.status_code == 200
    data = second.json()
    assert len(data["copied"]) == 0
    assert len(data["skipped"]) == len(ids)
    for item in data["skipped"]:
        assert item["status"] == "skipped"
