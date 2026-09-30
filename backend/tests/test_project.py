"""项目 CRUD 测试。"""
# pyright: reportCallIssue=false

from urllib.parse import parse_qs

import pytest
import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project

# 默认项目 id（由 alembic 迁移 10f6fdbf450e seed）
DEFAULT_PROJECT_ID = 1


@pytest_asyncio.fixture
async def projects(db_session: AsyncSession):
    """插入 4 个测试项目，id 范围 100-103（避开默认 id=1）。

    - id=100, 101: 无面积字段（默认 None）
    - id=102: 带 land_area
    - id=103: 同时带 land_area 和 building_area
    """
    objs = [
        Project(
            id=100,
            name="p-100",
            description="d-100",
            is_active=True,
        ),
        Project(
            id=101,
            name="p-101",
            description="d-101",
            is_active=True,
        ),
        Project(
            id=102,
            name="p-102",
            description="d-102",
            is_active=True,
            land_area=1200.0,
        ),
        Project(
            id=103,
            name="p-103",
            description="d-103",
            is_active=True,
            land_area=2000.0,
            building_area=1500.0,
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("", id="all"),
        pytest.param("page=1", id="page1_default_per_page"),
        pytest.param("page=1&per_page=2", id="page1_per_page2"),
        pytest.param("page=2&per_page=2", id="page2_per_page2"),
        pytest.param("page=10&per_page=2", id="page10_empty"),
    ],
)
async def test_list_projects(projects, client: AsyncClient, query: str):
    """默认项目（id=1）+ fixture 3 条，total 至少 4"""
    params = parse_qs(query.lstrip("?")) if query else {}
    page = int(params.get("page", [1])[0])
    # FastAPI 默认 per_page=10（参见 src/dependencies/public/pagination.py）
    per_page = int(params.get("per_page", [10])[0])
    expected_total = len(projects) + 1  # +1 for default project
    expected_items_count = min(per_page, max(0, expected_total - (page - 1) * per_page))

    resp = await client.get(f"/project?{query}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == expected_total
    assert len(data["items"]) == expected_items_count


@pytest.mark.parametrize(
    "p_id, exists",
    [
        pytest.param(DEFAULT_PROJECT_ID, True, id="default_project"),
        pytest.param(100, True, id="fixture_100"),
        pytest.param(101, True, id="fixture_101"),
        pytest.param(102, True, id="fixture_102_with_land"),
        pytest.param(103, True, id="fixture_103_with_both"),
        pytest.param(9999, False, id="not_found"),
    ],
)
async def test_get_project(projects, client: AsyncClient, p_id: int, exists: bool):
    resp = await client.get(f"/project/{p_id}")
    if exists:
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == p_id
        assert "name" in data
        assert "description" in data
        assert "is_active" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert "land_area" in data
        assert "building_area" in data
        # 验证 103 项目的面积字段值
        if p_id == 103:
            assert data["land_area"] == 2000.0
            assert data["building_area"] == 1500.0
        if p_id == 102:
            assert data["land_area"] == 1200.0
            assert data["building_area"] is None
    else:
        assert resp.status_code == 404


@pytest.mark.parametrize(
    "payload, code",
    [
        pytest.param({}, 422, id="missing_name"),
        pytest.param({"name": ""}, 422, id="empty_name"),
        pytest.param({"name": "x" * 101}, 422, id="too_long_name"),
        pytest.param(
            {"name": "x", "description": "y" * 501},
            422,
            id="too_long_description",
        ),
        pytest.param({"name": "new-p"}, 201, id="minimal"),
        pytest.param(
            {"name": "full", "description": "desc"},
            201,
            id="with_description",
        ),
        pytest.param(
            {"name": "with-area", "land_area": 1000.0, "building_area": 800.0},
            201,
            id="with_both_areas",
        ),
        pytest.param(
            {"name": "only-land", "land_area": 500.0},
            201,
            id="with_only_land_area",
        ),
        pytest.param(
            {"name": "only-building", "building_area": 300.0},
            201,
            id="with_only_building_area",
        ),
        pytest.param(
            {"name": "neg-land", "land_area": -1.0},
            422,
            id="negative_land_area",
        ),
        pytest.param(
            {"name": "neg-building", "building_area": -1.0},
            422,
            id="negative_building_area",
        ),
        pytest.param(
            {"name": "zero-land", "land_area": 0.0},
            201,
            id="zero_land_area_allowed",
        ),
    ],
)
async def test_create_project(client: AsyncClient, payload: dict, code: int):
    resp = await client.post("/project", json=payload)
    assert resp.status_code == code
    if resp.status_code == 201:
        data = resp.json()
        assert "id" in data
        assert data["name"] == payload["name"]
        assert data["is_active"] is True  # 默认值
        assert "created_at" in data
        assert "updated_at" in data
        # 面积字段验证（snake_case，匹配现有 ProjectResp 序列化）
        assert "land_area" in data
        assert "building_area" in data
        if "land_area" in payload:
            assert data["land_area"] == payload["land_area"]
        else:
            assert data["land_area"] is None
        if "building_area" in payload:
            assert data["building_area"] == payload["building_area"]
        else:
            assert data["building_area"] is None


async def test_create_project_with_basic_attributes(client: AsyncClient):
    """创建项目时可保存全部项目基础属性。"""
    payload = {
        "name": "完整项目",
        "province": "四川省",
        "city": "成都市",
        "address": "高新区天府大道 1 号",
        "land_area": 12000.0,
        "building_area": 30000.0,
        "underground_building_area": 8000.0,
        "aboveground_building_area": 22000.0,
        "structure_types": ["混凝土", "钢结构", "装配式结构"],
        "prefabrication_rate": 30.0,
        "design_service_life": 50,
        "structural_safety_level": "二级",
        "foundation_design_level": "乙级",
        "pile_foundation_design_level": "乙级",
        "fire_resistance_level": "二级",
        "seismic_fortification_intensity": "7度",
        "underground_waterproof_level": "一级",
        "planned_start_date": "2026-08-01",
        "planned_completion_date": "2028-07-31",
        "actual_start_date": "2026-08-10",
        "actual_completion_date": "2028-08-15",
        "construction_carbon_emission_limit": 12345.67,
    }

    resp = await client.post("/project", json=payload)

    assert resp.status_code == 201
    data = resp.json()
    for key, value in payload.items():
        assert data[key] == value

    get_resp = await client.get(f"/project/{data['id']}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    for key, value in payload.items():
        assert get_data[key] == value


async def test_create_project_basic_attributes_default_to_none(client: AsyncClient):
    """旧式最小创建保持兼容，新增字段默认均为空。"""
    resp = await client.post("/project", json={"name": "最小项目"})

    assert resp.status_code == 201
    data = resp.json()
    optional_fields = [
        "province",
        "city",
        "address",
        "underground_building_area",
        "aboveground_building_area",
        "structure_types",
        "prefabrication_rate",
        "design_service_life",
        "structural_safety_level",
        "foundation_design_level",
        "pile_foundation_design_level",
        "fire_resistance_level",
        "seismic_fortification_intensity",
        "underground_waterproof_level",
        "planned_start_date",
        "planned_completion_date",
        "actual_start_date",
        "actual_completion_date",
        "construction_carbon_emission_limit",
    ]
    assert all(data[field] is None for field in optional_fields)


@pytest.mark.parametrize(
    "field, value",
    [
        pytest.param("underground_building_area", -1, id="negative_underground_area"),
        pytest.param("aboveground_building_area", -1, id="negative_aboveground_area"),
        pytest.param("prefabrication_rate", -0.1, id="negative_prefabrication_rate"),
        pytest.param("prefabrication_rate", 100.1, id="excess_prefabrication_rate"),
        pytest.param("design_service_life", 0, id="non_positive_design_life"),
        pytest.param(
            "construction_carbon_emission_limit", -1, id="negative_carbon_limit"
        ),
        pytest.param("province", "省" * 51, id="province_too_long"),
        pytest.param("address", "址" * 256, id="address_too_long"),
        pytest.param("structural_safety_level", "级" * 21, id="safety_level_too_long"),
    ],
)
async def test_create_project_basic_attribute_validation(
    client: AsyncClient, field: str, value
):
    """项目基础属性应执行字段自身的范围和长度校验。"""
    resp = await client.post("/project", json={"name": "非法项目", field: value})

    assert resp.status_code == 422


@pytest.mark.parametrize(
    "field, value",
    [
        pytest.param("underground_building_area", 0, id="zero_underground_area"),
        pytest.param("aboveground_building_area", 0, id="zero_aboveground_area"),
        pytest.param("prefabrication_rate", 0, id="zero_prefabrication_rate"),
        pytest.param("prefabrication_rate", 100, id="full_prefabrication_rate"),
        pytest.param("construction_carbon_emission_limit", 0, id="zero_carbon_limit"),
    ],
)
async def test_create_project_basic_attribute_boundaries(
    client: AsyncClient, field: str, value
):
    """项目基础属性的合法边界值应被接受。"""
    resp = await client.post("/project", json={"name": "边界项目", field: value})

    assert resp.status_code == 201
    assert resp.json()[field] == value


@pytest.mark.parametrize(
    "p_id, payload, code",
    [
        pytest.param(9999, {"name": "x"}, 404, id="not_found"),
        pytest.param(100, {}, 200, id="empty_payload"),
        pytest.param(100, {"name": "updated"}, 200, id="update_name"),
        pytest.param(100, {"description": "new-desc"}, 200, id="update_description"),
        pytest.param(100, {"is_active": False}, 200, id="update_is_active"),
        pytest.param(100, {"name": "x" * 101}, 422, id="invalid_name"),
        pytest.param(
            100,
            {"name": "upd", "description": "d", "is_active": True},
            200,
            id="multiple",
        ),
        pytest.param(100, {"land_area": 500.0}, 200, id="update_land_area"),
        pytest.param(100, {"building_area": 300.0}, 200, id="update_building_area"),
        pytest.param(
            100,
            {"land_area": 800.0, "building_area": 600.0},
            200,
            id="update_both_areas",
        ),
        pytest.param(100, {"land_area": -1.0}, 422, id="negative_land_area_update"),
        pytest.param(
            100, {"building_area": -1.0}, 422, id="negative_building_area_update"
        ),
    ],
)
async def test_update_project(
    projects, client: AsyncClient, p_id: int, payload: dict, code: int
):
    resp = await client.put(f"/project/{p_id}", json=payload)
    assert resp.status_code == code
    if resp.status_code == 200 and payload:
        data = resp.json()
        assert data["id"] == p_id
        if "name" in payload:
            assert data["name"] == payload["name"]
        if "description" in payload:
            assert data["description"] == payload["description"]
        if "is_active" in payload:
            assert data["is_active"] == payload["is_active"]
        if "land_area" in payload:
            assert data["land_area"] == payload["land_area"]
        if "building_area" in payload:
            assert data["building_area"] == payload["building_area"]


async def test_update_project_basic_attributes(projects, client: AsyncClient):
    """新增项目属性支持部分更新且不会覆盖未提供字段。"""
    payload = {
        "province": "广东省",
        "city": "深圳市",
        "address": "南山区科技园",
        "structure_types": ["钢结构", "装配式结构"],
        "prefabrication_rate": 45.5,
        "planned_start_date": "2027-01-01",
        "construction_carbon_emission_limit": 9800.0,
    }

    resp = await client.put("/project/100", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    for key, value in payload.items():
        assert data[key] == value
    assert data["name"] == "p-100"
    assert data["description"] == "d-100"
    assert data["aboveground_building_area"] is None


async def test_update_project_basic_attribute_validation(projects, client: AsyncClient):
    """更新项目时同样校验新增字段。"""
    resp = await client.put("/project/100", json={"prefabrication_rate": 101})

    assert resp.status_code == 422


async def test_update_project_coordinates_must_be_paired(projects, client: AsyncClient):
    """经纬度成对校验：只给一半数值（含另一半显式 null）→ 422。

    成对提供（含同时 null）→ 200。
    """
    resp = await client.put("/project/100", json={"latitude": 30.0})
    assert resp.status_code == 422

    resp = await client.put("/project/100", json={"longitude": 120.0})
    assert resp.status_code == 422

    resp = await client.put("/project/100", json={"latitude": 30.0, "longitude": None})
    assert resp.status_code == 422

    resp = await client.put("/project/100", json={"latitude": 30.0, "longitude": 120.0})
    assert resp.status_code == 200
    assert resp.json()["latitude"] == 30.0
    assert resp.json()["longitude"] == 120.0

    resp = await client.put("/project/100", json={"latitude": None, "longitude": None})
    assert resp.status_code == 200
    assert resp.json()["latitude"] is None
    assert resp.json()["longitude"] is None


async def test_create_project_coordinates_must_be_paired(client: AsyncClient):
    """创建项目时经纬度同样成对校验。"""
    resp = await client.post("/project", json={"name": "坐标项目", "latitude": 30.0})
    assert resp.status_code == 422

    resp = await client.post("/project", json={"name": "坐标项目", "longitude": 120.0})
    assert resp.status_code == 422

    resp = await client.post(
        "/project", json={"name": "坐标项目", "latitude": 30.0, "longitude": 120.0}
    )
    assert resp.status_code == 201
    assert resp.json()["latitude"] == 30.0
    assert resp.json()["longitude"] == 120.0


@pytest.mark.parametrize(
    "payload, code",
    [
        pytest.param(
            {"name": "valid-region", "province": "四川省", "city": "成都市"},
            201,
            id="valid_province_city",
        ),
        pytest.param(
            {"name": "valid-municipality", "province": "北京市", "city": "北京市"},
            201,
            id="municipality_uses_same_name",
        ),
        pytest.param(
            {"name": "province-only", "province": "四川省"},
            201,
            id="province_only",
        ),
        pytest.param(
            {"name": "unknown-province", "province": "不存在省", "city": "成都市"},
            422,
            id="unknown_province",
        ),
        pytest.param(
            {"name": "unknown-city", "province": "四川省", "city": "北京市"},
            422,
            id="city_from_other_province",
        ),
        pytest.param(
            {"name": "district-as-city", "province": "北京市", "city": "东城区"},
            422,
            id="municipality_district_rejected",
        ),
    ],
)
async def test_create_project_region_validation(
    client: AsyncClient, payload: dict, code: int
):
    """创建项目时校验省市行政区划关系。"""
    resp = await client.post("/project", json=payload)

    assert resp.status_code == code


async def test_update_project_region_validation(projects, client: AsyncClient):
    """更新单个省市字段时使用数据库中的另一字段进行组合校验。"""
    valid_resp = await client.put(
        "/project/100", json={"province": "四川省", "city": "成都市"}
    )
    assert valid_resp.status_code == 200

    invalid_city_resp = await client.put("/project/100", json={"city": "北京市"})
    assert invalid_city_resp.status_code == 422

    invalid_province_resp = await client.put(
        "/project/100", json={"province": "北京市"}
    )
    assert invalid_province_resp.status_code == 422

    municipality_resp = await client.put(
        "/project/100", json={"province": "北京市", "city": "北京市"}
    )
    assert municipality_resp.status_code == 200


@pytest.mark.parametrize(
    "p_id, code",
    [
        pytest.param(9999, 404, id="not_found"),
        pytest.param(101, 204, id="success"),
    ],
)
async def test_delete_project(projects, client: AsyncClient, p_id: int, code: int):
    resp = await client.delete(f"/project/{p_id}")
    assert resp.status_code == code
    if code == 204:
        # 204 响应体为空
        assert resp.content == b""
        # 验证删除后 GET 返回 404
        get_resp = await client.get(f"/project/{p_id}")
        assert get_resp.status_code == 404
    else:
        # 404 响应体不为空（含 detail）
        assert resp.content != b""
        assert "detail" in resp.json()
