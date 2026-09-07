"""天气日记录数据库模型"""

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.weather import WeatherFields

from .mixin import ProjectScopeMixin, TimeStampMixin


class DailyWeather(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """天气日记录（降水 / 气温 / 光照，日粒度，手工与 Open-Meteo 同步同表）。"""

    __tablename__ = "daily_weather"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        sa.UniqueConstraint("project_id", "date", name="uq_daily_weather_project_date"),
    )

    id: int | None = Field(default=None, primary_key=True)

    date: WeatherFields.Day

    precipitation_mm: WeatherFields.PrecipitationMm
    temperature_c: WeatherFields.TemperatureC
    sunshine_hours: WeatherFields.SunshineHours

    is_synced: bool = Field(
        default=False, nullable=False, description="是否来自 Open-Meteo 自动同步"
    )


__all__ = ["DailyWeather"]
