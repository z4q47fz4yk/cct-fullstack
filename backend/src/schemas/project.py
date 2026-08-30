"""项目相关 schemas"""

import enum
from datetime import date
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from sqlmodel import SQLModel

from src.schemas.public.mixin import TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none
from src.utils.china_region import validate_province_city


class ProjectStatus(str, enum.Enum):
    """项目生命周期状态。"""

    PLANNING = "PLANNING"
    CONSTRUCTION = "CONSTRUCTION"
    COMPLETED = "COMPLETED"


class ProjectFields:
    """项目字段定义命名空间（仅约束 + 中文 description，不放 default / | None）。"""

    Name = Annotated[str, Field(min_length=1, max_length=100, description="项目名称")]
    Description = Annotated[
        str | None, Field(default=None, max_length=500, description="项目描述")
    ]
    LandArea = Annotated[
        float | None, Field(default=None, ge=0, description="占地面积（m²）")
    ]
    BuildingArea = Annotated[
        float | None, Field(default=None, ge=0, description="建筑面积（m²）")
    ]
    Province = Annotated[
        str | None, Field(default=None, max_length=50, description="项目所在省份")
    ]
    City = Annotated[
        str | None, Field(default=None, max_length=50, description="项目所在城市")
    ]
    Address = Annotated[
        str | None, Field(default=None, max_length=255, description="项目详细地址")
    ]
    UndergroundBuildingArea = Annotated[
        float | None, Field(default=None, ge=0, description="地下建筑面积（m²）")
    ]
    AbovegroundBuildingArea = Annotated[
        float | None, Field(default=None, ge=0, description="地上建筑面积（m²）")
    ]
    StructureTypes = Annotated[
        list[str] | None, Field(default=None, description="各楼宇结构形式标签")
    ]
    PrefabricationRate = Annotated[
        float | None, Field(default=None, ge=0, le=100, description="装配率（%）")
    ]
    DesignServiceLife = Annotated[
        int | None, Field(default=None, ge=1, description="设计使用年限（年）")
    ]
    StructuralSafetyLevel = Annotated[
        str | None, Field(default=None, max_length=20, description="结构安全等级")
    ]
    FoundationDesignLevel = Annotated[
        str | None, Field(default=None, max_length=20, description="基础设计等级")
    ]
    PileFoundationDesignLevel = Annotated[
        str | None, Field(default=None, max_length=20, description="桩基设计等级")
    ]
    FireResistanceLevel = Annotated[
        str | None, Field(default=None, max_length=20, description="建筑耐火等级")
    ]
    SeismicFortificationIntensity = Annotated[
        str | None, Field(default=None, max_length=20, description="抗震设防烈度")
    ]
    UndergroundWaterproofLevel = Annotated[
        str | None, Field(default=None, max_length=20, description="地下工程防水等级")
    ]
    PlannedStartDate = Annotated[
        date | None, Field(default=None, description="拟开工日期")
    ]
    PlannedCompletionDate = Annotated[
        date | None, Field(default=None, description="拟竣工日期")
    ]
    ActualStartDate = Annotated[
        date | None, Field(default=None, description="实际开工日期")
    ]
    ActualCompletionDate = Annotated[
        date | None, Field(default=None, description="实际竣工日期")
    ]
    ConstructionCarbonEmissionLimit = Annotated[
        float | None,
        Field(default=None, ge=0, description="施工阶段总碳排放量限额（tCO₂e）"),
    ]
    HousingResourceId = Annotated[
        int | None, Field(default=None, description="临时用房资源ID")
    ]
    WaterResourceId = Annotated[
        int | None, Field(default=None, description="外购水资源ID")
    ]
    ElectricityResourceId = Annotated[
        int | None, Field(default=None, description="外购电力资源ID")
    ]
    HousingSafetyFactor = Annotated[
        float, Field(default=1.2, ge=1.0, description="临时用房安全系数")
    ]
    PersonsPerRoom = Annotated[
        int, Field(default=4, ge=1, description="每间临时用房人数")
    ]
    IsActive = Annotated[bool, Field(default=True, description="是否正在施工")]
    Status = Annotated[ProjectStatus, Field(description="项目生命周期状态")]


class ProjectBase(SQLModel):
    """项目 schema 共享字段基类。

    继承 ``SQLModel``（不带 CamelCase alias）以保持项目 API 的 snake_case 字段命名，
    与历史 OpenAPI / 前端契约一致。
    """

    name: ProjectFields.Name
    description: ProjectFields.Description
    land_area: ProjectFields.LandArea
    building_area: ProjectFields.BuildingArea
    province: ProjectFields.Province
    city: ProjectFields.City
    address: ProjectFields.Address
    underground_building_area: ProjectFields.UndergroundBuildingArea
    aboveground_building_area: ProjectFields.AbovegroundBuildingArea
    structure_types: ProjectFields.StructureTypes
    prefabrication_rate: ProjectFields.PrefabricationRate
    design_service_life: ProjectFields.DesignServiceLife
    structural_safety_level: ProjectFields.StructuralSafetyLevel
    foundation_design_level: ProjectFields.FoundationDesignLevel
    pile_foundation_design_level: ProjectFields.PileFoundationDesignLevel
    fire_resistance_level: ProjectFields.FireResistanceLevel
    seismic_fortification_intensity: ProjectFields.SeismicFortificationIntensity
    underground_waterproof_level: ProjectFields.UndergroundWaterproofLevel
    planned_start_date: ProjectFields.PlannedStartDate
    planned_completion_date: ProjectFields.PlannedCompletionDate
    actual_start_date: ProjectFields.ActualStartDate
    actual_completion_date: ProjectFields.ActualCompletionDate
    construction_carbon_emission_limit: ProjectFields.ConstructionCarbonEmissionLimit
    housing_resource_id: ProjectFields.HousingResourceId
    water_resource_id: ProjectFields.WaterResourceId
    electricity_resource_id: ProjectFields.ElectricityResourceId
    housing_safety_factor: ProjectFields.HousingSafetyFactor
    persons_per_room: ProjectFields.PersonsPerRoom
    is_active: ProjectFields.IsActive
    status: Annotated[ProjectFields.Status, Field(default=ProjectStatus.CONSTRUCTION)]

    @model_validator(mode="after")
    def validate_region(self) -> "ProjectBase":
        validate_province_city(self.province, self.city)
        return self


class ProjectCreate(ProjectBase):
    """创建项目请求"""

    pass


class ProjectUpdate(SQLModel):
    """更新项目请求。

    NOT NULL 字段使用 ``Annotated[Alias, Field(default=None)]``：
    OpenAPI 不暴露 null 选项，``reject_explicit_none`` 在显式 null 时返回 422。
    其它 nullable 字段保持 ``T | None = Field(default=None)``。
    """

    # NOT NULL 数据库字段：不允许显式传 null
    name: Annotated[ProjectFields.Name, Field(default=None)]
    is_active: Annotated[ProjectFields.IsActive, Field(default=None)]
    status: Annotated[ProjectFields.Status, Field(default=None)]
    housing_safety_factor: Annotated[
        ProjectFields.HousingSafetyFactor, Field(default=None)
    ]
    persons_per_room: Annotated[ProjectFields.PersonsPerRoom, Field(default=None)]

    # DB nullable 字段：可显式传 null 表示清空
    description: ProjectFields.Description = Field(default=None)
    land_area: ProjectFields.LandArea = Field(default=None)
    building_area: ProjectFields.BuildingArea = Field(default=None)
    province: ProjectFields.Province = Field(default=None)
    city: ProjectFields.City = Field(default=None)
    address: ProjectFields.Address = Field(default=None)
    underground_building_area: ProjectFields.UndergroundBuildingArea = Field(
        default=None
    )
    aboveground_building_area: ProjectFields.AbovegroundBuildingArea = Field(
        default=None
    )
    structure_types: ProjectFields.StructureTypes = Field(default=None)
    prefabrication_rate: ProjectFields.PrefabricationRate = Field(default=None)
    design_service_life: ProjectFields.DesignServiceLife = Field(default=None)
    structural_safety_level: ProjectFields.StructuralSafetyLevel = Field(default=None)
    foundation_design_level: ProjectFields.FoundationDesignLevel = Field(default=None)
    pile_foundation_design_level: ProjectFields.PileFoundationDesignLevel = Field(
        default=None
    )
    fire_resistance_level: ProjectFields.FireResistanceLevel = Field(default=None)
    seismic_fortification_intensity: ProjectFields.SeismicFortificationIntensity = (
        Field(default=None)
    )
    underground_waterproof_level: ProjectFields.UndergroundWaterproofLevel = Field(
        default=None
    )
    planned_start_date: ProjectFields.PlannedStartDate = Field(default=None)
    planned_completion_date: ProjectFields.PlannedCompletionDate = Field(default=None)
    actual_start_date: ProjectFields.ActualStartDate = Field(default=None)
    actual_completion_date: ProjectFields.ActualCompletionDate = Field(default=None)
    # ruff: noqa: E501 (alias name too long to fit line limit without breaking annotation)
    construction_carbon_emission_limit: ProjectFields.ConstructionCarbonEmissionLimit = Field(
        default=None
    )  # noqa: E501
    housing_resource_id: ProjectFields.HousingResourceId = Field(default=None)
    water_resource_id: ProjectFields.WaterResourceId = Field(default=None)
    electricity_resource_id: ProjectFields.ElectricityResourceId = Field(default=None)

    @field_validator(
        "name",
        "is_active",
        "status",
        "housing_safety_factor",
        "persons_per_room",
        mode="before",
    )
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)

    @model_validator(mode="after")
    def validate_region(self) -> "ProjectUpdate":
        validate_province_city(self.province, self.city)
        return self


class ProjectResp(ProjectBase, TimeStampRespMixin):
    """项目响应"""

    id: int = Field(description="项目ID")
    is_active: bool = Field(description="是否活跃")


__all__ = ["ProjectCreate", "ProjectUpdate", "ProjectResp"]
