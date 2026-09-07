"""Open-Meteo 历史天气同步服务（日粒度）。

数据源：``archive-api.open-meteo.com/v1/archive``（ERA5 再分析等，覆盖 1940 →
今天，免费无需 API key）。通过 ``openmeteo_requests.AsyncClient``（FlatBuffers
传输）请求 ``daily`` 聚合变量：

- ``temperature_2m_mean`` → 平均气温（℃）
- ``precipitation_sum`` → 日降水总量（mm，含雨雪）
- ``sunshine_duration`` → 日光照时长（秒，WMO 晴照定义，入库折算为小时）

时间语义：请求时传 ``timezone=auto``，服务端按项目所在地返回本地日期行，
返回的行数与请求天数一致，按天对齐即可（不做 epoch 换算——UTC+8 等正偏移
时 epoch 会跨到前一天）。

同步策略（幂等 + 手工优先）：
- 已存在且 ``is_synced=True`` 的行：数值相同则跳过（不计数），有差异则更新；
- 已存在且 ``is_synced=False`` 的行（手工录入）：**不覆盖**，计入 ``skipped``；
- 不存在 → 插入新行（``is_synced=True``）。
"""

import datetime as dt
from dataclasses import dataclass

import numpy as np
from openmeteo_requests import AsyncClient
from openmeteo_sdk.Variable import Variable
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.models.weather import DailyWeather
from src.schemas.weather import WeatherSyncResp
from src.utils.query import project_filter

# 秒 → 小时（sunshine_duration 返回秒）
_SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True)
class DailyWeatherPoint:
    """单个日期的天气数值（缺失字段为 None）。"""

    date: dt.date
    temperature_c: float | None
    precipitation_mm: float | None
    sunshine_hours: float | None


def _as_float(values: np.ndarray, index: int, round_digits: int) -> float | None:
    """取 numpy float32 值转 Python float；NaN / 越界 → None。"""
    if index < 0 or index >= len(values):
        return None
    raw = values[index]
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    return round(float(raw), round_digits)


async def fetch_archive_daily(
    latitude: float,
    longitude: float,
    start_date: dt.date,
    end_date: dt.date,
    *,
    archive_url: str | None = None,
    timeout_s: float | None = None,
) -> list[DailyWeatherPoint]:
    """从 Open-Meteo 历史归档 API 拉取日天气。

    Args:
        latitude / longitude: 项目坐标（WGS84）。
        start_date / end_date: 同步日期窗口（含两端）。
        archive_url: 归档 API 地址，缺省取 settings.weather_archive_url。
        timeout_s: 请求超时，缺省取 settings.weather_sync_timeout_s。

    Returns:
        窗口内每天一个点，行数与窗口天数一致（缺失变量为 None）。

    Raises:
        OpenMeteoRequestsError: 网络 / HTTP 4xx / FlatBuffers 流错误。
        ValueError: 返回行数与窗口不符（数据结构异常）。
    """
    url = archive_url or settings.weather_archive_url
    timeout = timeout_s or settings.weather_sync_timeout_s
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": [
            "temperature_2m_mean",
            "precipitation_sum",
            "sunshine_duration",
        ],
        "timezone": "auto",
    }
    client = AsyncClient()
    responses = await client.weather_api(url, params=params, timeout=timeout)
    if not responses:
        raise ValueError("天气服务返回空响应")
    daily = responses[0].Daily()
    if daily is None:
        raise ValueError("天气服务未返回每日数据")

    # 按请求顺序的变量匹配（不依赖服务端顺序）
    values_by_variable: dict[int, np.ndarray] = {}
    for i in range(daily.VariablesLength()):
        var = daily.Variables(i)
        if var is None:
            continue
        values_by_variable[var.Variable()] = var.ValuesAsNumpy()

    def variable(name: int) -> np.ndarray | None:
        return values_by_variable.get(name)

    temperature = variable(Variable.temperature)
    precipitation = variable(Variable.precipitation)
    sunshine = variable(Variable.sunshine_duration)

    expected_days = (end_date - start_date).days + 1
    lengths = {
        length
        for arr in (temperature, precipitation, sunshine)
        if arr is not None
        for length in [len(arr)]
    }
    if lengths and expected_days not in lengths:
        raise ValueError(
            f"天气数据行数异常：期望 {expected_days} 天，实际 {sorted(lengths)}"
        )

    points: list[DailyWeatherPoint] = []
    for offset in range(expected_days):
        day = start_date + dt.timedelta(days=offset)
        temp = _as_float(temperature, offset, 2) if temperature is not None else None
        precip = (
            _as_float(precipitation, offset, 2) if precipitation is not None else None
        )
        sunshine_s = _as_float(sunshine, offset, 2) if sunshine is not None else None
        sunshine_h = (
            round(sunshine_s / _SECONDS_PER_HOUR, 1) if sunshine_s is not None else None
        )
        points.append(
            DailyWeatherPoint(
                date=day,
                temperature_c=temp,
                precipitation_mm=precip,
                sunshine_hours=sunshine_h,
            )
        )
    return points


class WeatherSyncService:
    """Open-Meteo 历史天气同步服务（stateful，构造注入 session 与 project_id）。"""

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    async def sync(
        self,
        latitude: float,
        longitude: float,
        start_date: dt.date,
        end_date: dt.date,
    ) -> WeatherSyncResp:
        """拉取并幂等写入窗口内日天气。

        Args:
            latitude / longitude: 项目坐标。
            start_date / end_date: 已由路由裁剪到 [最早, 今天] 的窗口。

        Returns:
            同步统计（synced 写入/更新数、skipped 手工跳过数、实际窗口）。

        Raises:
            OpenMeteoRequestsError / ValueError: 透传 fetch 异常（路由转 502）。
        """
        points = await fetch_archive_daily(latitude, longitude, start_date, end_date)

        existing_rows = (
            await self.session.exec(
                project_filter(
                    select(DailyWeather).where(
                        col(DailyWeather.date).between(start_date, end_date)
                    ),
                    DailyWeather,
                    self.project_id,
                )
            )
        ).all()
        by_date: dict[dt.date, DailyWeather] = {row.date: row for row in existing_rows}

        synced = 0
        skipped = 0
        to_add: list[DailyWeather] = []
        to_update: list[DailyWeather] = []

        for point in points:
            existing = by_date.get(point.date)
            numeric = {
                "temperature_c": point.temperature_c,
                "precipitation_mm": point.precipitation_mm,
                "sunshine_hours": point.sunshine_hours,
            }
            if existing is None:
                to_add.append(
                    DailyWeather(
                        project_id=self.project_id,
                        date=point.date,
                        is_synced=True,
                        **numeric,
                    )
                )
                synced += 1
                continue

            if not existing.is_synced:
                # 手工录入优先：不覆盖
                skipped += 1
                continue

            changed = False
            for key, value in numeric.items():
                if getattr(existing, key) != value:
                    setattr(existing, key, value)
                    changed = True
            if changed:
                to_update.append(existing)
                synced += 1

        self.session.add_all(to_add)
        for row in to_update:
            self.session.add(row)
        await self.session.commit()

        message = (
            f"已同步 {start_date} ~ {end_date}"
            f"（写入/更新 {synced} 条，跳过手工记录 {skipped} 条）"
        )
        return WeatherSyncResp(
            synced=synced,
            skipped=skipped,
            start_date=start_date,
            end_date=end_date,
            message=message,
        )


__all__ = [
    "DailyWeatherPoint",
    "WeatherSyncService",
    "fetch_archive_daily",
]
