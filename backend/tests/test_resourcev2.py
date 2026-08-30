# pyright: reportCallIssue=false
from urllib.parse import parse_qs

import pytest
import pytest_asyncio
from faker import Faker
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project
from src.models.resource import Resource
from src.models.tag import ResourceTag, Tag, TagDimension
from src.schemas.resource import ResourceCategory

# 默认项目 id（由 alembic 迁移 10f6fdbf450e seed）
PID = 1


@pytest_asyncio.fixture
async def resources(db_session: AsyncSession):
    fake = Faker("zh_CN")
    available_names = ["name1", "name2", "name3"]

    r = [
        Resource(
            # 确保只有 id 10000-10008 存在于数据库中
            id=i + 10000,
            project_id=PID,
            # 确保只有 available_names 中的值位于数据库中
            name=f"{fake.random_element(available_names)}-{i + 1}",
            description="c" + fake.sentence(),  # 确保不以 c 开头的值不存在于数据库中
            category=fake.enum(ResourceCategory),
        )
        for i in range(9)
    ]

    db_session.add_all(r)
    await db_session.commit()
    return r


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("", id="all"),
        #
        pytest.param("page=1", id="pagination1"),
        pytest.param("page=2&per_page=2", id="pagination2"),
        pytest.param("page=4&per_page=3", id="pagination3"),
        #
        pytest.param("name=name1", id="filter_by_name1"),
        pytest.param("name=ame1", id="filter_by_name2"),
        pytest.param("name=name", id="filter_by_name3"),
        #
        pytest.param("category=labor", id="filter_by_category1"),
        pytest.param("category=machinery", id="filter_by_category2"),
        pytest.param("category=material", id="filter_by_category3"),
        pytest.param("category=transport", id="filter_by_category4"),
        #
        pytest.param("category=labor&name=name1", id="filter_by_both"),
        pytest.param("category=labor&name=name1&per_page=3", id="filter_with_pagi"),
    ],
)
async def test_list_resources(resources, client: AsyncClient, query: str):
    """计算预期值时考虑 alembic seed 的预存资源（cctv2-test 库有 800+ 条）

    通过 client 调用 `/projects/{PID}/resource?per_page=1000` 拿全量 base
    （绕过 router 默认 per_page=20 上限），再叠加 fixture 数据。
    """
    base_resp = await client.get(f"/projects/{PID}/resource?per_page=1000")
    base_items = base_resp.json()["items"]

    # fixture 资源 id=1-9，base 中可能也有同 id 数据；按 id 去重
    by_id: dict[int, Resource] = {}
    for it in base_items:
        by_id[it["id"]] = Resource(
            id=it["id"],
            project_id=PID,
            name=it["name"],
            category=ResourceCategory(it["category"]),
        )
    for r in resources:
        if r.id is not None and r.id not in by_id:
            by_id[r.id] = r
    all_resources = list(by_id.values())

    def calc_expected(q: str, all_r: list[Resource]) -> tuple[int, int]:
        params = parse_qs(q.lstrip("?"))

        name = params.get("name", [None])[0]
        category_str = params.get("category", [None])[0]
        category: ResourceCategory | None = (
            ResourceCategory(category_str) if category_str else None
        )
        # FastAPI 默认 per_page=10（参见 src/dependencies/public/pagination.py）
        page = int(params.get("page", [1])[0])
        per_page = int(params.get("per_page", [10])[0])

        filtered = all_r
        if name:
            filtered = [r for r in filtered if name in r.name]
        if category:
            filtered = [r for r in filtered if r.category == category]

        total = len(filtered)
        offset = (page - 1) * per_page
        items_count = min(per_page, max(0, total - offset))
        return total, items_count

    resp = await client.get(f"/projects/{PID}/resource?{query}")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data

    expected_total, expected_length = calc_expected(query, all_resources)
    assert data["total"] == expected_total
    assert len(data["items"]) == expected_length


@pytest.mark.parametrize(
    "selector, code",
    [
        pytest.param("first", 200, id="first_resource"),
        pytest.param("second", 200, id="second_resource"),
        pytest.param("missing", 404, id="missing"),
    ],
)
async def test_get_resource(resources, selector: str, code: int, client: AsyncClient):
    ids = [r.id for r in resources if r.id is not None]
    r_id = {"first": ids[0], "second": ids[1], "missing": 99999}[selector]
    resp = await client.get(f"/projects/{PID}/resource/{r_id}")
    assert resp.status_code == code
    if code == 200:
        data = resp.json()
        assert data["id"] == r_id
        assert "name" in data
        assert "description" in data
        assert "category" in data
        assert "createdAt" in data
        assert "updatedAt" in data
    # 不用验证错误信息，运行错误信息变化


@pytest.mark.parametrize(
    "payload, code",
    [
        pytest.param({}, 422, id="invalid_payload"),
        pytest.param({"name": "name1", "description": "d"}, 422, id="invalid_payload"),
        pytest.param(
            {"description": "d", "category": "machinery"},
            422,
            id="invalid_payload",
        ),
        pytest.param({"name": "d", "category": "machinery"}, 422, id="invalid_payload"),
        pytest.param(
            {"name": "name1", "description": "d", "category": "labor"},
            201,
            id="minimal",
        ),
        pytest.param(
            {"name": "", "description": "d", "category": "labor"},
            422,
            id="empty_name",
        ),
        pytest.param(
            {"name": "d" * 101, "description": "d", "category": "labor"},
            422,
            id="too_long_name",
        ),
        pytest.param(
            {"name": "d" * 100, "description": "d" * 501, "category": "labor"},
            422,
            id="too_long_description",
        ),
        pytest.param(
            {"name": "d" * 100, "description": "d" * 500, "category": "l"},
            422,
            id="invalid_category",
        ),
    ],
)
async def test_create_resource(client: AsyncClient, payload: dict, code: int):
    resp = await client.post(f"/projects/{PID}/resource", json=payload)
    assert resp.status_code == code
    if resp.status_code == 200:
        data = resp.json()
        assert "id" in data
        assert "createdAt" in data
        assert "updatedAt" in data


@pytest.mark.parametrize(
    "rid, payload, code",
    [
        pytest.param("first", {}, 200, id="empty_payload"),
        pytest.param(0, {}, 404, id="invalid_id"),
        #
        pytest.param("first", {"name": "name0"}, 200, id="partial update"),
        pytest.param("first", {"description": "d-special"}, 200, id="partial update"),
        pytest.param("first", {"category": "machinery"}, 200, id="partial update"),
        pytest.param("first", {"unit": "m4"}, 200, id="partial update"),
        pytest.param("first", {"unitPrice": 98.4}, 200, id="partial update"),
        pytest.param("first", {"carbonFactor": 34.5}, 200, id="partial update"),
        #
        pytest.param(
            "first", {"carbonFactor": 9, "unitPrice": 40}, 200, id="multiple update"
        ),
        #
        pytest.param("first", {"name": "d" * 101}, 422, id="invalid name"),
        pytest.param(
            "first", {"description": "d" * 501}, 422, id="invalid description"
        ),
        pytest.param("first", {"category": "test"}, 422, id="invalid category"),
    ],
)
async def test_update_resource(
    resources, client: AsyncClient, rid, payload: dict, code: int
):
    r_id = resources[0].id if rid == "first" else rid
    resp = await client.put(f"/projects/{PID}/resource/{r_id}", json=payload)
    assert resp.status_code == code
    if resp.status_code == 200:
        data = resp.json()
        assert "id" in data
        assert "createdAt" in data
        assert "updatedAt" in data
        if not payload:
            # payload 为空时，不会触发更新
            return

        for k, v in payload.items():
            assert k in data
            assert data[k] == v
        if "category" in payload:
            if payload["category"] == resources[0].category.value:
                # 值相同时，不会触发更新
                return
        assert data["createdAt"] != data["updatedAt"]


@pytest.mark.parametrize(
    "rid, code",
    [
        pytest.param(0, 404, id="invalid_id"),
        pytest.param("first", 204, id="success"),
    ],
)
async def test_delete_resource(resources, client: AsyncClient, rid, code: int):
    r_id = resources[0].id if rid == "first" else rid
    resp = await client.delete(f"/projects/{PID}/resource/{r_id}")
    assert resp.status_code == code


# ============================================================
# 列表携带直接标签（include_tags 开关）
# ============================================================


@pytest_asyncio.fixture
async def tag_dimension(db_session: AsyncSession) -> TagDimension:
    d = TagDimension(project_id=PID, name="测试维度", description="d")
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    return d


@pytest_asyncio.fixture
async def tag_resources(db_session: AsyncSession) -> list[Resource]:
    """三个命名唯一的资源（tagtest-*），避免与 seed 数据混淆。"""
    rs = [
        Resource(
            project_id=PID,
            name=f"tagtest-r{i}",
            description="d",
            category=ResourceCategory.material,
        )
        for i in range(1, 4)
    ]
    db_session.add_all(rs)
    await db_session.commit()
    for r in rs:
        await db_session.refresh(r)
    return rs


async def _add_resource_tags(
    db_session: AsyncSession,
    links: list[tuple[int, int]],
) -> None:
    for rid, tid in links:
        db_session.add(ResourceTag(project_id=PID, resource_id=rid, tag_id=tid))
    await db_session.commit()


async def test_list_resources_tags_empty_by_default(client: AsyncClient, tag_resources):
    """默认不带 include_tags 时，每个资源返回空 tags 列表。"""
    resp = await client.get(f"/projects/{PID}/resource?name=tagtest&per_page=100")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {it["name"] for it in items} == {"tagtest-r1", "tagtest-r2", "tagtest-r3"}
    assert all(it["tags"] == [] for it in items)


async def test_list_resources_include_tags(
    client: AsyncClient,
    db_session: AsyncSession,
    tag_resources,
    tag_dimension,
):
    """include_tags=true 时返回直接标签（按 ID 升序），无标签资源返回空数组。"""
    r1, r2, r3 = tag_resources
    tag_a = Tag(
        project_id=PID, dimension_id=tag_dimension.id, name="tagtest-A", description="d"
    )
    tag_b = Tag(
        project_id=PID, dimension_id=tag_dimension.id, name="tagtest-B", description="d"
    )
    db_session.add_all([tag_a, tag_b])
    await db_session.commit()
    await db_session.refresh(tag_a)
    await db_session.refresh(tag_b)
    assert tag_a.id is not None and tag_b.id is not None
    assert r1.id is not None and r2.id is not None and r3.id is not None

    await _add_resource_tags(
        db_session,
        [
            (r1.id, tag_b.id),  # 故意乱序写入，验证按 tag_id 升序返回
            (r1.id, tag_a.id),
            (r2.id, tag_a.id),
            # r3 不挂标签
        ],
    )

    resp = await client.get(
        f"/projects/{PID}/resource?name=tagtest&include_tags=true&per_page=100"
    )
    assert resp.status_code == 200
    by_name = {it["name"]: it for it in resp.json()["items"]}

    assert [t["name"] for t in by_name["tagtest-r1"]["tags"]] == [
        "tagtest-A",
        "tagtest-B",
    ]
    assert [t["name"] for t in by_name["tagtest-r2"]["tags"]] == ["tagtest-A"]
    assert by_name["tagtest-r3"]["tags"] == []


async def test_list_resources_include_tags_pagination(
    client: AsyncClient,
    db_session: AsyncSession,
    tag_resources,
    tag_dimension,
):
    """分页只加载当前页资源的标签，跨页不串数据。"""
    r1, r2, r3 = tag_resources
    tag_a = Tag(
        project_id=PID, dimension_id=tag_dimension.id, name="tagtest-A", description="d"
    )
    db_session.add(tag_a)
    await db_session.commit()
    await db_session.refresh(tag_a)
    assert tag_a.id is not None
    assert r1.id is not None and r2.id is not None and r3.id is not None
    await _add_resource_tags(
        db_session,
        [(r1.id, tag_a.id), (r2.id, tag_a.id), (r3.id, tag_a.id)],
    )

    # page=1 取 r1；page=2 取 r2（按 id 升序）
    resp = await client.get(
        f"/projects/{PID}/resource?name=tagtest&include_tags=true&per_page=1&page=2"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "tagtest-r2"
    assert [t["name"] for t in items[0]["tags"]] == ["tagtest-A"]


async def test_list_resources_include_tags_project_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
    tag_resources,
    tag_dimension,
):
    """其他项目挂同名标签的资源不串入本项目列表。"""
    r1, r2, r3 = tag_resources
    tag_a = Tag(
        project_id=PID, dimension_id=tag_dimension.id, name="tagtest-A", description="d"
    )
    db_session.add(tag_a)
    await db_session.commit()
    await db_session.refresh(tag_a)
    assert tag_a.id is not None and r1.id is not None

    other = Project(name="Tag 隔离项目", is_active=True)
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    assert other.id is not None
    other_res = Resource(
        project_id=other.id,
        name="tagtest-other",
        description="d",
        category=ResourceCategory.material,
    )
    other_tag = Tag(
        project_id=other.id,
        dimension_id=tag_dimension.id,
        name="tagtest-A",
        description="d",
    )
    db_session.add_all([other_res, other_tag])
    await db_session.commit()
    await db_session.refresh(other_res)
    await db_session.refresh(other_tag)
    assert other_res.id is not None and other_tag.id is not None
    db_session.add(
        ResourceTag(
            project_id=other.id,
            resource_id=other_res.id,
            tag_id=other_tag.id,
        )
    )
    await db_session.commit()

    # 本项目 r1 挂上同名的 tagtest-A
    await _add_resource_tags(db_session, [(r1.id, tag_a.id)])

    resp = await client.get(
        f"/projects/{PID}/resource?name=tagtest&include_tags=true&per_page=100"
    )
    assert resp.status_code == 200
    by_name = {it["name"]: it for it in resp.json()["items"]}
    assert "tagtest-other" not in by_name
    assert [t["name"] for t in by_name["tagtest-r1"]["tags"]] == ["tagtest-A"]
    assert by_name["tagtest-r2"]["tags"] == []
    assert by_name["tagtest-r3"]["tags"] == []


async def test_list_resources_include_tags_with_filters(
    client: AsyncClient,
    db_session: AsyncSession,
    tag_resources,
    tag_dimension,
):
    """include_tags 与 name/category 过滤组合使用。"""
    r1, r2, r3 = tag_resources
    tag_a = Tag(
        project_id=PID, dimension_id=tag_dimension.id, name="tagtest-A", description="d"
    )
    db_session.add(tag_a)
    await db_session.commit()
    await db_session.refresh(tag_a)
    assert tag_a.id is not None and r1.id is not None and r2.id is not None
    await _add_resource_tags(
        db_session,
        [(r1.id, tag_a.id), (r2.id, tag_a.id)],
    )

    resp = await client.get(
        f"/projects/{PID}/resource?name=tagtest-r1&include_tags=true&per_page=100"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "tagtest-r1"
    assert [t["name"] for t in items[0]["tags"]] == ["tagtest-A"]
