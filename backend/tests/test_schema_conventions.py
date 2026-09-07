"""Model/Schema 契约回归测试。"""
# pyright: reportCallIssue=false

import pytest
from pydantic import BaseModel, ValidationError

from src.app import app
from src.schemas.optimize import ResourceConstraintUpdate
from src.schemas.project import ProjectUpdate
from src.schemas.resource import ResourceUpdate
from src.schemas.resource_reuse_config import ResourceReuseConfigUpdate
from src.schemas.resource_usage import ResourceUsageUpdate
from src.schemas.task import TaskUpdate

# ---------------------------------------------------------------------------
# 常量：每个 Update 类的 NOT NULL / nullable 字段集合（OpenAPI property 名）
# ---------------------------------------------------------------------------

_STRICT: dict[type[BaseModel], set[str]] = {
    TaskUpdate: {"code", "name", "duration", "completed"},
    ProjectUpdate: {
        "name",
        "is_active",
        "housing_safety_factor",
        "persons_per_room",
    },
    ResourceUpdate: {
        "name",
        "description",
        "category",
        "unit",
        "unit_price",
        "carbon_factor",
    },
    ResourceUsageUpdate: {
        "task_id",
        "resource_id",
        "usage_date",
        "quantity",
        "usage_type",
    },
    ResourceReuseConfigUpdate: {"max_reuses", "reuse_count", "affect_cost"},
    ResourceConstraintUpdate: {"max_usage", "description"},
}

_NULLABLE: dict[type[BaseModel], set[str]] = {
    TaskUpdate: {"description"},
    ProjectUpdate: {
        "description",
        "land_area",
        "building_area",
        "province",
        "city",
        "address",
        "latitude",
        "longitude",
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
        "housing_resource_id",
    },
    ResourceUpdate: set(),  # 所有字段均为 NOT NULL
    ResourceUsageUpdate: set(),  # 所有字段均为 NOT NULL
    ResourceReuseConfigUpdate: {"description"},
    ResourceConstraintUpdate: set(),  # 所有字段均为 NOT NULL
}

_ALL_UPDATES: tuple[type[BaseModel], ...] = (
    TaskUpdate,
    ProjectUpdate,
    ResourceUpdate,
    ResourceUsageUpdate,
    ResourceReuseConfigUpdate,
    ResourceConstraintUpdate,
)


# =============================================================================
# 1) NOT NULL 字段拒绝显式 null（原有 6 字段 + 全量扩展）
# =============================================================================


def _param_strict():
    """返回 (Schema, field) 组合——测试显式 null 被拒绝。"""
    for schema_cls in _ALL_UPDATES:
        for field in sorted(_STRICT[schema_cls]):
            yield pytest.param(schema_cls, field, id=f"{schema_cls.__name__}-{field}")


@pytest.mark.parametrize(("schema", "field"), list(_param_strict()))
def test_update_schema_rejects_null_for_not_null_column(schema, field: str):
    """非空数据库字段不接受显式 null，但仍可从请求中省略。"""
    assert schema().model_dump(exclude_unset=True) == {}

    with pytest.raises(ValidationError):
        schema.model_validate({field: None})


# =============================================================================
# 2) nullable 字段接受并保留显式 null
# =============================================================================


def _param_nullable():
    """返回 (Schema, field) 组合——测试显式 null 被接受并保存。"""
    for schema_cls in _ALL_UPDATES:
        for field in sorted(_NULLABLE[schema_cls]):
            yield pytest.param(schema_cls, field, id=f"{schema_cls.__name__}-{field}")


@pytest.mark.parametrize(("schema", "field"), list(_param_nullable()))
def test_update_schema_preserves_null_for_nullable_column(schema, field: str):
    """可空数据库字段保留显式 null，以便 PUT 清空字段。"""
    payload = schema.model_validate({field: None})

    assert payload.model_dump(exclude_unset=True) == {field: None}


# =============================================================================
# 3) 所有 Update 类的 Optional-to-provide 契约
# =============================================================================


@pytest.mark.parametrize("schema_cls", _ALL_UPDATES)
def test_every_update_schema_dump_empty_when_no_fields(schema_cls):
    """省略所有字段时 exclude_unset 应产生空字典（语义：不覆盖任何旧值）。"""
    assert schema_cls().model_dump(exclude_unset=True) == {}


# =============================================================================
# 4) OpenAPI 字段为空 required + 属性可空性对齐
# =============================================================================


def test_update_openapi_fields_are_not_required():
    """部分更新 DTO 的字段在 OpenAPI 中均可省略。"""
    schemas = app.openapi()["components"]["schemas"]

    for name in (
        "ProjectUpdate",
        "TaskUpdate",
        "ResourceUpdate",
        "ResourceUsageUpdate",
        "ResourceReuseConfigUpdate",
        "ResourceConstraintUpdate",
    ):
        assert not schemas[name].get("required"), f"{name} should have no required"


def _openapi_key(schema_cls, snake_name: str) -> str:
    """将模块内字段名映射为 OpenAPI property 名。

    ProjectUpdate 使用 snake_case（继承 SQLModel），其余使用 camelCase。
    """
    if schema_cls is ProjectUpdate:
        return snake_name
    # 简单 snake→camel：去掉前导下划线分段
    parts = snake_name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def test_update_openapi_strict_fields_exclude_null():
    """NOT NULL 字段在 OpenAPI 中不暴露 {type: null} 分支，若有 default 则为 null。"""
    schemas = app.openapi()["components"]["schemas"]

    for schema_cls in _ALL_UPDATES:
        name = schema_cls.__name__
        props = schemas[name]["properties"]
        for field in _STRICT[schema_cls]:
            key = _openapi_key(schema_cls, field)
            prop = props[key]
            # Not nullable：不包含 anyOf null 分支
            assert "anyOf" not in prop or not any(
                opt.get("type") == "null" for opt in prop.get("anyOf", [])
            ), f"{name}.{key} should not advertise null; got {prop}"
            # When "default" appears it must be null (Pydantic may elide for bool/int)
            if "default" in prop:
                assert prop["default"] is None, (
                    f"{name}.{key} default should be null; got {prop}"
                )


def test_update_openapi_nullable_fields_include_null():
    """nullable 字段在 OpenAPI 中暴露 {type: null} 分支。"""
    schemas = app.openapi()["components"]["schemas"]

    for schema_cls in _ALL_UPDATES:
        name = schema_cls.__name__
        props = schemas[name]["properties"]
        for field in _NULLABLE[schema_cls]:
            key = _openapi_key(schema_cls, field)
            prop = props[key]
            # Must have anyOf with a null type
            null_opts = [
                opt for opt in prop.get("anyOf", []) if opt.get("type") == "null"
            ]
            assert null_opts, f"{name}.{key} should include {{type: null}}; got {prop}"
