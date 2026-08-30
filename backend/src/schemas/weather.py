"""天气月度记录相关 schemas。"""

from datetime import date
from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin


class WeatherFields:
    """天气字段定义命名空间。"""

    Month = Annotated[date, Field(description="月份（每月1日）")]
    PrecipitationMm = Annotated[
        float | None, Field(default=None, ge=0, description="降水量（mm）")
    ]
    TemperatureC = Annotated[
        float | None, Field(default=None, description="平均气温（℃）")
    ]
    SunshineHours = Annotated[
        float | None, Field(default=None, ge=0, description="光照时长（h）")
    ]


class WeatherCreate(CamelCaseRespMixin):
    """创建天气月度记录。"""

    month: WeatherFields.Month
    precipitation_mm: WeatherFields.PrecipitationMm
    temperature_c: WeatherFields.TemperatureC
    sunshine_hours: WeatherFields.SunshineHours

    @field_validator("month")
    @classmethod
    def validate_month_first_day(cls, value: date) -> date:
        """月份必须为每月 1 日。"""
        if value.day != 1:
            raise ValueError("month 必须为每月 1 日")
        return value


class WeatherUpdate(CamelCaseRespMixin):
    """更新天气月度记录（month 不可改，数值字段显式 null 表示清空）。"""

    precipitation_mm: WeatherFields.PrecipitationMm
    temperature_c: WeatherFields.TemperatureC
    sunshine_hours: WeatherFields.SunshineHours


class WeatherResp(CamelCaseRespMixin, TimeStampRespMixin):
    """天气月度记录响应。"""

    id: int = Field(description="记录ID")
    project_id: int = Field(description="项目ID")
    month: date = Field(description="月份（每月1日）")
    precipitation_mm: float | None = Field(default=None, description="降水量（mm）")
    temperature_c: float | None = Field(default=None, description="平均气温（℃）")
    sunshine_hours: float | None = Field(default=None, description="光照时长（h）")


__all__ = ["WeatherCreate", "WeatherUpdate", "WeatherResp"]
