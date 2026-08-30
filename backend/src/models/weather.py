"""天气月度记录数据库模型"""

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.weather import WeatherFields

from .mixin import ProjectScopeMixin, TimeStampMixin


class MonthlyWeather(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """天气月度记录（降水 / 气温 / 光照，v1 纯展示）。"""

    __tablename__ = "monthly_weather"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id", "month", name="uq_monthly_weather_project_month"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    month: WeatherFields.Month

    precipitation_mm: WeatherFields.PrecipitationMm
    temperature_c: WeatherFields.TemperatureC
    sunshine_hours: WeatherFields.SunshineHours


__all__ = ["MonthlyWeather"]
