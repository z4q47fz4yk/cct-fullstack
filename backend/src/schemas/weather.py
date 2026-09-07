"""天气日记录相关 schemas。"""

from datetime import date as date_type
from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin


class WeatherFields:
    """天气字段定义命名空间。"""

    Day = Annotated[date_type, Field(description="日期（日粒度）")]
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
    """创建天气日记录。"""

    date: WeatherFields.Day
    precipitation_mm: WeatherFields.PrecipitationMm
    temperature_c: WeatherFields.TemperatureC
    sunshine_hours: WeatherFields.SunshineHours


class WeatherUpdate(CamelCaseRespMixin):
    """更新天气日记录（date 不可改，数值字段显式 null 表示清空）。"""

    precipitation_mm: WeatherFields.PrecipitationMm
    temperature_c: WeatherFields.TemperatureC
    sunshine_hours: WeatherFields.SunshineHours


class WeatherResp(CamelCaseRespMixin, TimeStampRespMixin):
    """天气日记录响应。"""

    id: int = Field(description="记录ID")
    project_id: int = Field(description="项目ID")
    date: WeatherFields.Day
    precipitation_mm: float | None = Field(default=None, description="降水量（mm）")
    temperature_c: float | None = Field(default=None, description="平均气温（℃）")
    sunshine_hours: float | None = Field(default=None, description="光照时长（h）")
    is_synced: bool = Field(default=False, description="是否来自 Open-Meteo 自动同步")


class WeatherSyncRequest(CamelCaseRespMixin):
    """天气同步请求（可选日期窗口；省略时取项目实际/拟开工到今天）。"""

    start_date: date_type | None = Field(default=None, description="起始日期（含）")
    end_date: date_type | None = Field(default=None, description="结束日期（含）")


class WeatherSyncResp(CamelCaseRespMixin):
    """天气同步响应。"""

    synced: int = Field(ge=0, description="本次写入/更新（含覆盖）的记录数")
    skipped: int = Field(ge=0, description="跳过的记录数（手工录入优先，未覆盖）")
    start_date: date_type = Field(description="实际同步起始日期")
    end_date: date_type = Field(description="实际同步结束日期")
    message: str = Field(description="结果说明")


__all__ = [
    "WeatherCreate",
    "WeatherUpdate",
    "WeatherResp",
    "WeatherSyncRequest",
    "WeatherSyncResp",
]
