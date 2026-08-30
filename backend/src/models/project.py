"""项目数据库模型"""

from typing import Annotated

import sqlalchemy as sa
from sqlalchemy import Column, text
from sqlmodel import Field, SQLModel

from src.schemas.project import ProjectFields, ProjectStatus

from .mixin import TimeStampMixin
from .pydantic_json import PydanticJson


class Project(TimeStampMixin, SQLModel, table=True):
    """项目

    字段约束来自 ``src.schemas.project.ProjectFields``；
    本文件仅保留 SQLModel / SQLAlchemy 特有的 DB 配置。
    """

    __tablename__ = "project"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)

    name: ProjectFields.Name

    description: ProjectFields.Description

    # TODO: 未来破坏性变更：以 status 为唯一事实来源，移除 is_active 列。
    #       （现保留列并随 status 同步，兼容既有 API/前端/测试。）
    is_active: ProjectFields.IsActive

    land_area: ProjectFields.LandArea

    building_area: ProjectFields.BuildingArea

    province: ProjectFields.Province

    city: ProjectFields.City

    address: ProjectFields.Address

    underground_building_area: ProjectFields.UndergroundBuildingArea

    aboveground_building_area: ProjectFields.AbovegroundBuildingArea

    structure_types: Annotated[
        ProjectFields.StructureTypes,
        Field(sa_column=Column(PydanticJson(list[str]), nullable=True)),
    ]

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

    housing_resource_id: Annotated[
        ProjectFields.HousingResourceId,
        Field(foreign_key="resource.id", ondelete="SET NULL", nullable=True),
    ]

    water_resource_id: Annotated[
        ProjectFields.WaterResourceId,
        Field(foreign_key="resource.id", ondelete="SET NULL", nullable=True),
    ]

    electricity_resource_id: Annotated[
        ProjectFields.ElectricityResourceId,
        Field(foreign_key="resource.id", ondelete="SET NULL", nullable=True),
    ]

    housing_safety_factor: Annotated[
        ProjectFields.HousingSafetyFactor,
        Field(nullable=False, sa_column_kwargs={"server_default": text("1.2")}),
    ]

    persons_per_room: Annotated[
        ProjectFields.PersonsPerRoom,
        Field(nullable=False, sa_column_kwargs={"server_default": text("4")}),
    ]

    status: Annotated[
        ProjectFields.Status,
        Field(
            default=ProjectStatus.CONSTRUCTION,
            sa_column=sa.Column(
                sa.String(length=20),
                nullable=False,
                server_default="CONSTRUCTION",
            ),
        ),
    ]


__all__ = ["Project"]
