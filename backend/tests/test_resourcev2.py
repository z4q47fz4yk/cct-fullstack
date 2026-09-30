# pyright: reportCallIssue=false
from urllib.parse import parse_qs

import pytest
import pytest_asyncio
from faker import Faker
from httpx2 import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.optimize import ResourceConstraint
from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.tag import ResourceTag, Tag
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
        pytest.param(
            {
                "name": "test-负碳光伏",
                "description": "负碳因子资源",
                "category": "others",
                "unit": "kWh",
                "unitPrice": 0,
                "carbonFactor": -0.5,
            },
            201,
            id="negative_carbon_factor_allowed",
        ),
        pytest.param(
            {
                "name": "越界单价",
                "description": "d",
                "category": "labor",
                "unitPrice": 1e9 + 1,
            },
            422,
            id="unit_price_over_limit",
        ),
        pytest.param(
            {
                "name": "越界碳因子下限",
                "description": "d",
                "category": "labor",
                "carbonFactor": -1e9 - 1,
            },
            422,
            id="carbon_factor_below_limit",
        ),
        pytest.param(
            {
                "name": "越界碳因子上限",
                "description": "d",
                "category": "labor",
                "carbonFactor": 1e9 + 1,
            },
            422,
            id="carbon_factor_over_limit",
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
        # 负碳因子合法（如光伏抵消）；单价 / 碳因子超上限拒绝
        pytest.param("first", {"carbonFactor": -0.5}, 200, id="negative carbon factor"),
        pytest.param("first", {"unitPrice": 1e9 + 1}, 422, id="unit price over limit"),
        pytest.param(
            "first", {"carbonFactor": -1e9 - 1}, 422, id="carbon factor below limit"
        ),
        pytest.param(
            "first", {"carbonFactor": 1e9 + 1}, 422, id="carbon factor over limit"
        ),
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
):
    """include_tags=true 返回直接标签（按 ID 升序）＋分类默认标签。

    三个 tagtest-* 资源均属 material 分类，在项目默认标签（材料 is_default）
    存在时，返回 tags = [材料(默认)] + 直接挂载标签，按 tag_id 升序。
    """
    r1, r2, r3 = tag_resources
    tag_a = Tag(project_id=PID, name="tagtest-A", group="测试", description="d")
    tag_b = Tag(project_id=PID, name="tagtest-B", group="测试", description="d")
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
            # r3 不挂直接标签
        ],
    )

    resp = await client.get(
        f"/projects/{PID}/resource?name=tagtest&include_tags=true&per_page=100"
    )
    assert resp.status_code == 200
    by_name = {it["name"]: it for it in resp.json()["items"]}

    # 默认分类标签 id < 直接标签 id → 排序后「材料」恒在最前
    assert [t["name"] for t in by_name["tagtest-r1"]["tags"]] == [
        "材料",
        "tagtest-A",
        "tagtest-B",
    ]
    assert [t["name"] for t in by_name["tagtest-r2"]["tags"]] == ["材料", "tagtest-A"]
    # 无直接标签的资源仍带其分类默认标签（材料）
    assert [t["name"] for t in by_name["tagtest-r3"]["tags"]] == ["材料"]


async def test_list_resources_include_tags_pagination(
    client: AsyncClient,
    db_session: AsyncSession,
    tag_resources,
):
    """分页只加载当前页资源的标签，跨页不串数据。"""
    r1, r2, r3 = tag_resources
    tag_a = Tag(project_id=PID, name="tagtest-A", group="测试", description="d")
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
    assert [t["name"] for t in items[0]["tags"]] == ["材料", "tagtest-A"]


async def test_list_resources_include_tags_project_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
    tag_resources,
):
    """其他项目挂同名标签的资源不串入本项目列表。"""
    r1, r2, r3 = tag_resources
    tag_a = Tag(project_id=PID, name="tagtest-A", group="测试", description="d")
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
        name="tagtest-A",
        group="其他项目",
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
    assert [t["name"] for t in by_name["tagtest-r1"]["tags"]] == ["材料", "tagtest-A"]
    assert [t["name"] for t in by_name["tagtest-r2"]["tags"]] == ["材料"]
    assert [t["name"] for t in by_name["tagtest-r3"]["tags"]] == ["材料"]


async def test_list_resources_include_tags_with_filters(
    client: AsyncClient,
    db_session: AsyncSession,
    tag_resources,
):
    """include_tags 与 name/category 过滤组合使用。"""
    r1, r2, r3 = tag_resources
    tag_a = Tag(project_id=PID, name="tagtest-A", group="测试", description="d")
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
    assert [t["name"] for t in items[0]["tags"]] == ["材料", "tagtest-A"]


# ============================================================
# constrained / reusable 过滤 & include_constraint / include_reuse_config
# ============================================================


@pytest_asyncio.fixture
async def cfg_resources(db_session: AsyncSession):
    """两个材料类资源（cfgr-*）用于测试 constrained/reusable 过滤"""
    rs = [
        Resource(
            project_id=PID,
            name=f"cfgr-r{i}",
            description="d",
            category=ResourceCategory.material,
        )
        for i in range(1, 3)
    ]
    db_session.add_all(rs)
    await db_session.commit()
    for r in rs:
        await db_session.refresh(r)
    return rs


@pytest_asyncio.fixture
async def cfg_data(db_session: AsyncSession, cfg_resources):
    """在 cfg_resources 上插入约束（r1）+ 周转配置（r2）"""
    r1, r2 = cfg_resources
    constraint = ResourceConstraint(
        project_id=PID,
        resource_id=r1.id,
        max_usage=100.0,
        description="cfg-c",
    )
    reuse = ResourceReuseConfig(
        project_id=PID,
        resource_id=r2.id,
        max_reuses=3,
        reuse_count=2,
        affect_cost=False,
        description="cfg-r",
    )
    db_session.add_all([constraint, reuse])
    await db_session.commit()
    await db_session.refresh(constraint)
    await db_session.refresh(reuse)
    return r1, r2, constraint, reuse


@pytest.mark.parametrize(
    "query, expected_names",
    [
        pytest.param(
            "constrained=true",
            {"cfgr-r1"},
            id="constrained_only_returns_with_constraint",
        ),
        pytest.param(
            "reusable=true",
            {"cfgr-r2"},
            id="reusable_only_returns_with_reuse",
        ),
        pytest.param(
            "constrained=true&reusable=false",
            {"cfgr-r1"},
            id="constrained_true_reusable_false",
        ),
        pytest.param(
            "constrained=false&reusable=false",
            {"cfgr-r1", "cfgr-r2"},
            id="both_false_returns_all",
        ),
    ],
)
async def test_list_resources_filter_by_config(
    cfg_data,
    client: AsyncClient,
    query: str,
    expected_names: set[str],
):
    """constrained / reusable 过滤：按约束/复用过滤项目内资源（互斥校验）"""
    resp = await client.get(f"/projects/{PID}/resource?{query}&name=cfgr&per_page=100")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {it["name"] for it in items} == expected_names


async def test_list_resources_constrained_and_reusable_mutex(
    cfg_data, client: AsyncClient
):
    """constrained=true 与 reusable=true 同时为 true 返回 422。"""
    resp = await client.get(
        f"/projects/{PID}/resource?constrained=true&reusable=true&name=cfgr&per_page=100"
    )
    assert resp.status_code == 422
    assert "互斥" in resp.json()["detail"]


async def test_list_resources_include_constraint_and_reuse_config(
    cfg_data, client: AsyncClient
):
    """include_constraint / include_reuse_config 填充对应字段；未开启时字段为 null。"""
    r1, r2, constraint, reuse = cfg_data

    # 仅 include_constraint
    resp = await client.get(
        f"/projects/{PID}/resource?include_constraint=true&name=cfgr&per_page=100"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    by_name = {it["name"]: it for it in items}
    # r1 有约束 → constraint 字段填充
    assert by_name["cfgr-r1"]["constraint"] is not None
    assert by_name["cfgr-r1"]["constraint"]["maxUsage"] == 100.0
    assert by_name["cfgr-r1"]["constraint"]["resourceId"] == r1.id
    # r2 无约束 → constraint 为 null
    assert by_name["cfgr-r2"]["constraint"] is None
    # reuseConfig 未开启 → null
    assert by_name["cfgr-r1"]["reuseConfig"] is None
    assert by_name["cfgr-r2"]["reuseConfig"] is None

    # 同时 include_constraint + include_reuse_config
    resp = await client.get(
        f"/projects/{PID}/resource?include_constraint=true"
        "&include_reuse_config=true&name=cfgr&per_page=100"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    by_name = {it["name"]: it for it in items}
    assert by_name["cfgr-r1"]["constraint"] is not None
    assert by_name["cfgr-r1"]["reuseConfig"] is None
    assert by_name["cfgr-r2"]["constraint"] is None
    assert by_name["cfgr-r2"]["reuseConfig"] is not None
    assert by_name["cfgr-r2"]["reuseConfig"]["maxReuses"] == 3
    assert by_name["cfgr-r2"]["reuseConfig"]["reuseCount"] == 2
    assert by_name["cfgr-r2"]["reuseConfig"]["resourceId"] == r2.id


async def test_list_resources_default_response_has_null_config(
    cfg_data, client: AsyncClient
):
    """默认不带 include_* 时，constraint / reuseConfig 字段为 null（兼容旧契约）。"""
    resp = await client.get(f"/projects/{PID}/resource?name=cfgr&per_page=100")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for it in items:
        assert it["constraint"] is None
        assert it["reuseConfig"] is None


async def test_list_resources_filter_combined_with_config(
    cfg_data, client: AsyncClient
):
    """constrained=true + include_constraint=true：有约束的资源附带 constraint。"""
    resp = await client.get(
        f"/projects/{PID}/resource?constrained=true&include_constraint=true"
        "&name=cfgr&per_page=100"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "cfgr-r1"
    assert items[0]["constraint"] is not None
    assert items[0]["constraint"]["maxUsage"] == 100.0
    assert items[0]["reuseConfig"] is None


async def test_list_resources_filter_isolation_between_projects(
    cfg_data, db_session: AsyncSession, client: AsyncClient
):
    """其他项目的约束/复用配置不串入本项目列表。"""
    r1, r2, constraint, reuse = cfg_data
    other = Project(name="Cfg 隔离项目", is_active=True)
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    assert other.id is not None
    # 在其他项目为 r1/r2 的同名资源建约束/配置
    other_r1 = Resource(
        project_id=other.id,
        name="cfgr-r1",
        description="d",
        category=ResourceCategory.material,
    )
    other_r2 = Resource(
        project_id=other.id,
        name="cfgr-r2",
        description="d",
        category=ResourceCategory.material,
    )
    db_session.add_all([other_r1, other_r2])
    await db_session.commit()
    await db_session.refresh(other_r1)
    await db_session.refresh(other_r2)
    assert other_r1.id is not None and other_r2.id is not None
    db_session.add_all([
        ResourceConstraint(
            project_id=other.id, resource_id=other_r1.id, max_usage=999.0
        ),
        ResourceReuseConfig(
            project_id=other.id,
            resource_id=other_r2.id,
            max_reuses=9,
            reuse_count=9,
            affect_cost=True,
        ),
    ])
    await db_session.commit()

    # constrained=true 时 r1 应被命中，r2 不应；response 内的 constraint 来自本项目
    resp = await client.get(
        f"/projects/{PID}/resource?constrained=true&include_constraint=true"
        "&name=cfgr&per_page=100"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [it["name"] for it in items] == ["cfgr-r1"]
    assert items[0]["constraint"]["maxUsage"] == 100.0  # 不是 999

    # reusable=true 同理
    resp = await client.get(
        f"/projects/{PID}/resource?reusable=true&include_reuse_config=true"
        "&name=cfgr&per_page=100"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [it["name"] for it in items] == ["cfgr-r2"]
    assert items[0]["reuseConfig"]["reuseCount"] == 2  # 不是 9


# ============================================================
# tag_ids AND 过滤
# ============================================================


@pytest_asyncio.fixture
async def tag_id_resources(db_session: AsyncSession):
    """四个 tagid-* 资源用于 AND 过滤测试"""
    rs = [
        Resource(
            project_id=PID,
            name=f"tagid-r{i}",
            description="d",
            category=ResourceCategory.material,
        )
        for i in range(1, 5)
    ]
    db_session.add_all(rs)
    await db_session.commit()
    for r in rs:
        await db_session.refresh(r)
    return rs


async def _make_tag(db_session: AsyncSession, name: str) -> Tag:
    tag = Tag(project_id=PID, name=name, group="测试", description="d")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    assert tag.id is not None
    return tag


async def _link(db_session: AsyncSession, rid: int, tid: int) -> None:
    db_session.add(ResourceTag(project_id=PID, resource_id=rid, tag_id=tid))
    await db_session.commit()


@pytest.mark.parametrize(
    "links, query_tag_ids, expected_names",
    [
        # 单标签：所有挂该标签的资源
        pytest.param(
            [("tagid-r1", "tagid-A"), ("tagid-r2", "tagid-A")],
            ["tagid-A"],
            {"tagid-r1", "tagid-r2"},
            id="single_tag",
        ),
        # 双标签 AND：仅同时挂 A 与 B 的资源
        pytest.param(
            [
                ("tagid-r1", "tagid-A"),
                ("tagid-r2", "tagid-A"),
                ("tagid-r2", "tagid-B"),
                ("tagid-r3", "tagid-B"),
            ],
            ["tagid-A", "tagid-B"],
            {"tagid-r2"},
            id="two_tags_and",
        ),
        # 三标签 AND：必须三个都有
        pytest.param(
            [
                ("tagid-r1", "tagid-A"),
                ("tagid-r2", "tagid-A"),
                ("tagid-r2", "tagid-B"),
                ("tagid-r2", "tagid-C"),
                ("tagid-r3", "tagid-A"),
                ("tagid-r3", "tagid-B"),
            ],
            ["tagid-A", "tagid-B", "tagid-C"],
            {"tagid-r2"},
            id="three_tags_and",
        ),
    ],
)
async def test_list_resources_tag_ids_and(
    db_session: AsyncSession,
    tag_id_resources,
    links: list[tuple[str, str]],
    query_tag_ids: list[str],
    expected_names: set[str],
    client: AsyncClient,
):
    """tag_ids 多个值之间为 AND 关系。"""
    r_by_name = {r.name: r for r in tag_id_resources}
    tag_cache: dict[str, Tag] = {}

    for rname, tname in links:
        tag = tag_cache.get(tname) or await _make_tag(db_session, tname)
        tag_cache[tname] = tag
        r = r_by_name[rname]
        assert r.id is not None
        assert tag.id is not None
        await _link(db_session, r.id, tag.id)

    qs = "&".join(f"tag_ids={tag_cache[t].id}" for t in query_tag_ids)
    resp = await client.get(f"/projects/{PID}/resource?{qs}&name=tagid&per_page=100")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {it["name"] for it in items} == expected_names


async def test_list_resources_tag_ids_empty_returns_all(
    tag_id_resources, client: AsyncClient
):
    """tag_ids 不传时不过滤。"""
    resp = await client.get(f"/projects/{PID}/resource?name=tagid&per_page=100")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {it["name"] for it in items} == {
        "tagid-r1",
        "tagid-r2",
        "tagid-r3",
        "tagid-r4",
    }


async def test_list_resources_tag_ids_combined_with_category(
    db_session: AsyncSession,
    tag_id_resources,
    client: AsyncClient,
):
    """tag_ids 与 category 组合：AND 在所有过滤条件下生效。"""
    # 给 r1/r2 挂 tagid-X；改 r3 的分类为 labor
    tag_x = await _make_tag(db_session, "tagid-X")
    r1, r2, r3, _ = tag_id_resources
    assert all(r.id is not None for r in (r1, r2, r3))
    assert tag_x.id is not None
    await _link(db_session, r1.id, tag_x.id)
    await _link(db_session, r2.id, tag_x.id)

    r3.category = ResourceCategory.labor
    db_session.add(r3)
    await db_session.commit()

    # 仅 category=material：r1/r2/r4 都属于 material（fixture 默认）
    resp = await client.get(
        f"/projects/{PID}/resource?category=material&tag_ids={tag_x.id}"
        "&name=tagid&per_page=100"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {it["name"] for it in items} == {"tagid-r1", "tagid-r2"}

    # 仅 category=labor（不带 tag_ids）：r3 应被命中（但 r3 没挂 X，仍命中）
    resp = await client.get(
        f"/projects/{PID}/resource?category=labor&name=tagid&per_page=100"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {it["name"] for it in items} == {"tagid-r3"}


async def test_list_resources_tag_ids_pagination(
    db_session: AsyncSession,
    tag_id_resources,
    client: AsyncClient,
):
    """tag_ids 与分页组合：total / items 计数一致。"""
    tag_x = await _make_tag(db_session, "tagid-P")
    r1, r2, r3, _ = tag_id_resources
    assert all(r.id is not None for r in (r1, r2, r3))
    assert tag_x.id is not None
    await _link(db_session, r1.id, tag_x.id)
    await _link(db_session, r2.id, tag_x.id)
    await _link(db_session, r3.id, tag_x.id)

    resp = await client.get(
        f"/projects/{PID}/resource?tag_ids={tag_x.id}&name=tagid&per_page=2&page=1"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    resp = await client.get(
        f"/projects/{PID}/resource?tag_ids={tag_x.id}&name=tagid&per_page=2&page=2"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 1


async def _default_tag_by_name(db_session: AsyncSession, name: str) -> Tag | None:
    """取项目内指定名称的默认分类标签（由 alembic 10f6fdbf450e seed）。"""
    return (
        await db_session.exec(
            select(Tag).where(
                Tag.project_id == PID,
                Tag.is_default == True,  # noqa: E712
                Tag.name == name,
            )
        )
    ).first()


async def test_list_resources_tag_ids_default_label_matches_category(
    db_session: AsyncSession,
    tag_id_resources,
    client: AsyncClient,
):
    """按默认分类标签（如"材料" is_default=true）筛选时，
    命中该分类下的资源（默认标签由资源类别派生，与 include_tags 返回的 tags 口径一致）。
    """
    default_tag = await _default_tag_by_name(db_session, "材料")
    if default_tag is None or default_tag.id is None:
        pytest.skip("项目内不存在默认标签「材料」")

    # fixture 中 r1/r2/r3/r4 都是 material 类，按「材料」应全部命中
    resp = await client.get(
        f"/projects/{PID}/resource?tag_ids={default_tag.id}&name=tagid&per_page=100"
    )
    assert resp.status_code == 200
    assert {it["name"] for it in resp.json()["items"]} == {
        "tagid-r1",
        "tagid-r2",
        "tagid-r3",
        "tagid-r4",
    }


async def test_list_resources_tag_ids_default_label_consistent_with_include_tags(
    db_session: AsyncSession,
    tag_id_resources,
    client: AsyncClient,
):
    """默认分类标签筛选结果与 include_tags 返回的 tags 完全一致：
    命中的每个资源都带该默认标签，未命中的都不带。
    """
    default_tag = await _default_tag_by_name(db_session, "材料")
    if default_tag is None or default_tag.id is None:
        pytest.skip("项目内不存在默认标签「材料」")

    resp = await client.get(
        f"/projects/{PID}/resource?tag_ids={default_tag.id}&name=tagid"
        "&include_tags=true&per_page=100"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items
    for it in items:
        assert any(t["id"] == default_tag.id for t in it["tags"])

    # 未按默认标签过滤的全量列表里，material 类资源的 tags 同样含该默认标签
    resp_all = await client.get(
        f"/projects/{PID}/resource?name=tagid&include_tags=true&per_page=100"
    )
    assert resp_all.status_code == 200
    for it in resp_all.json()["items"]:
        has_default = any(t["id"] == default_tag.id for t in it["tags"])
        assert has_default == (it["id"] in {x["id"] for x in items})


async def test_list_resources_tag_ids_default_label_and_custom_tag(
    db_session: AsyncSession,
    tag_id_resources,
    client: AsyncClient,
):
    """默认分类标签与自建标签之间保持 AND 语义：
    默认标签按类别派生命中，自建标签按 resource_tag 直接挂载命中。
    """
    default_material = await _default_tag_by_name(db_session, "材料")
    default_labor = await _default_tag_by_name(db_session, "人工")
    if (
        default_material is None
        or default_material.id is None
        or default_labor is None
        or default_labor.id is None
    ):
        pytest.skip("项目内不存在默认标签「材料」/「人工」")

    r1, r2, r3, _ = tag_id_resources
    assert all(r.id is not None for r in (r1, r2, r3))
    tag_a = await _make_tag(db_session, "tagid-A")
    assert tag_a.id is not None
    await _link(db_session, r1.id, tag_a.id)
    await _link(db_session, r2.id, tag_a.id)
    # r3 改为 labor 类并挂同一自建标签：不应被「材料」命中
    r3.category = ResourceCategory.labor
    db_session.add(r3)
    await db_session.commit()
    await _link(db_session, r3.id, tag_a.id)

    # 「材料」默认标签 AND tagid-A：r1/r2（material + 挂 A）
    resp = await client.get(
        f"/projects/{PID}/resource?tag_ids={default_material.id}&tag_ids={tag_a.id}"
        "&name=tagid&per_page=100"
    )
    assert resp.status_code == 200
    assert {it["name"] for it in resp.json()["items"]} == {"tagid-r1", "tagid-r2"}

    # 「人工」默认标签 AND tagid-A：仅 r3（labor + 挂 A）
    resp = await client.get(
        f"/projects/{PID}/resource?tag_ids={default_labor.id}&tag_ids={tag_a.id}"
        "&name=tagid&per_page=100"
    )
    assert resp.status_code == 200
    assert {it["name"] for it in resp.json()["items"]} == {"tagid-r3"}


async def test_list_resources_tag_ids_project_isolation(
    db_session: AsyncSession,
    tag_id_resources,
    client: AsyncClient,
):
    """其他项目为同名标签挂的 resource_tag 不串入本项目列表。"""
    other = Project(name="TagIds 隔离项目", is_active=True)
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    assert other.id is not None

    other_tag = Tag(project_id=other.id, name="tagid-O", description="d")
    db_session.add(other_tag)
    await db_session.commit()
    await db_session.refresh(other_tag)
    assert other_tag.id is not None

    # 在其他项目为 tagid-r1 建 resource_tag
    r1 = tag_id_resources[0]
    assert r1.id is not None
    db_session.add(
        ResourceTag(project_id=other.id, resource_id=r1.id, tag_id=other_tag.id)
    )
    await db_session.commit()

    # 本项目用同名标签过滤应不命中（项目隔离）
    resp = await client.get(
        f"/projects/{PID}/resource?tag_ids={other_tag.id}&name=tagid&per_page=100"
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []
