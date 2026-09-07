"""天气日记录 + Open-Meteo 同步端点测试。"""
# pyright: reportCallIssue=false

import datetime as dt
from datetime import date

import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project, ProjectStatus
from src.services import weather_sync as weather_sync_module
from src.services.weather_sync import DailyWeatherPoint

# 相对"今天"的偏移生成日期，保证用例不随运行日期漂移
_TODAY = date.today()


def _d(offset_days: int) -> str:
    """today ± offset 的 ISO 日期串（负=过去）。"""
    return (_TODAY + dt.timedelta(days=offset_days)).isoformat()


def _pt(
    offset_days: int,
    temp: float | None,
    rain: float | None,
    sun: float | None,
) -> DailyWeatherPoint:
    return DailyWeatherPoint(
        date=_TODAY + dt.timedelta(days=offset_days),
        temperature_c=temp,
        precipitation_mm=rain,
        sunshine_hours=sun,
    )


@pytest_asyncio.fixture
async def wx_project(db_session: AsyncSession) -> int:
    """带拟开工日（30 天前，默认窗口在 max_days 内）的独立项目（无经纬度）。"""
    project = Project(
        name="wx-project",
        description="weather sync tests",
        planned_start_date=_TODAY - dt.timedelta(days=30),
        status=ProjectStatus.CONSTRUCTION,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    assert project.id is not None
    return project.id


async def _set_coords(
    client: AsyncClient, pid: int, lat: float = 39.9075, lon: float = 116.39723
) -> None:
    resp = await client.put(
        f"/project/{pid}",
        json={"latitude": lat, "longitude": lon},
    )
    assert resp.status_code == 200
    assert resp.json()["latitude"] == lat
    assert resp.json()["longitude"] == lon


async def test_project_lat_lon_validation(client: AsyncClient, wx_project):
    """经纬度越界 → 422。"""
    resp = await client.put(f"/project/{wx_project}", json={"latitude": 95.0})
    assert resp.status_code == 422
    resp = await client.put(f"/project/{wx_project}", json={"longitude": -181.0})
    assert resp.status_code == 422

    resp = await client.put(
        f"/project/{wx_project}", json={"latitude": 30.5, "longitude": 120.1}
    )
    assert resp.status_code == 200
    # 显式 null 可清空
    resp = await client.put(f"/project/{wx_project}", json={"latitude": None})
    assert resp.status_code == 200
    assert resp.json()["latitude"] is None


async def test_sync_requires_coords(client: AsyncClient, wx_project):
    """未设经纬度 → 422。"""
    resp = await client.post(
        f"/projects/{wx_project}/weather/sync",
        json={"startDate": _d(-5), "endDate": _d(-3)},
    )
    assert resp.status_code == 422
    assert "经纬度" in resp.json()["detail"]


async def test_sync_window_validation(client: AsyncClient, wx_project):
    """窗口校验：未来日期 / 起大于止 / 超范围。"""
    await _set_coords(client, wx_project)

    resp = await client.post(
        f"/projects/{wx_project}/weather/sync",
        json={"startDate": _d(-5), "endDate": _d(10)},
    )
    assert resp.status_code == 422
    assert "仅支持到今天" in resp.json()["detail"]

    resp = await client.post(
        f"/projects/{wx_project}/weather/sync",
        json={"startDate": _d(-1), "endDate": _d(-3)},
    )
    assert resp.status_code == 422
    assert "不能晚于" in resp.json()["detail"]

    # 超 max_days（settings.weather_sync_max_days=370）
    resp = await client.post(
        f"/projects/{wx_project}/weather/sync",
        json={"startDate": _d(-400), "endDate": _d(0)},
    )
    assert resp.status_code == 422
    assert "范围过大" in resp.json()["detail"]


async def test_sync_happy_path_hermetic(client: AsyncClient, wx_project, monkeypatch):
    """同步成功：stub fetch 返回固定点 → 写入 + 幂等。"""
    await _set_coords(client, wx_project)

    start_day, end_day = -3, -1

    async def fake_fetch(lat, lon, start, end, **kwargs):
        assert start == _TODAY + dt.timedelta(days=start_day)
        assert end == _TODAY + dt.timedelta(days=end_day)
        return [
            _pt(-3, 3.2, 0.5, 2.5),
            _pt(-2, 1.1, None, 0.0),
            _pt(-1, -2.0, 12.0, None),
        ]

    monkeypatch.setattr(weather_sync_module, "fetch_archive_daily", fake_fetch)

    resp = await client.post(
        f"/projects/{wx_project}/weather/sync",
        json={"startDate": _d(start_day), "endDate": _d(end_day)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["synced"] == 3
    assert data["skipped"] == 0
    assert data["startDate"] == _d(start_day)
    assert data["endDate"] == _d(end_day)

    # 幂等：再次同步不再新增
    resp = await client.post(
        f"/projects/{wx_project}/weather/sync",
        json={"startDate": _d(start_day), "endDate": _d(end_day)},
    )
    assert resp.json()["synced"] == 0

    # 列表读取：isSynced 标记 + 数值
    resp = await client.get(
        f"/projects/{wx_project}/weather?startDate={_d(start_day)}&endDate={_d(0)}"
    )
    items = resp.json()["items"]
    assert len(items) == 3
    by_day = {w["date"]: w for w in items}
    assert by_day[_d(-3)]["temperatureC"] == 3.2
    assert by_day[_d(-3)]["precipitationMm"] == 0.5
    assert by_day[_d(-2)]["sunshineHours"] == 0.0
    assert all(w["isSynced"] is True for w in items)


async def test_sync_respects_manual_records(
    client: AsyncClient, wx_project, monkeypatch
):
    """手工记录（is_synced=False）不被同步覆盖，计入 skipped。"""
    await _set_coords(client, wx_project)

    # 先手工录入 -2 / -1（-1 只填温度）
    await client.post(
        f"/projects/{wx_project}/weather",
        json={"date": _d(-2), "temperatureC": 9.9, "precipitationMm": 3.0},
    )
    await client.post(
        f"/projects/{wx_project}/weather",
        json={"date": _d(-1), "temperatureC": -2.0},
    )

    async def fake_fetch(lat, lon, start, end, **kwargs):
        return [
            _pt(-3, 3.2, 0.5, 2.5),
            _pt(-2, 1.1, 0.2, 1.0),
            _pt(-1, -2.0, 12.0, 6.0),
        ]

    monkeypatch.setattr(weather_sync_module, "fetch_archive_daily", fake_fetch)

    resp = await client.post(
        f"/projects/{wx_project}/weather/sync",
        json={"startDate": _d(-3), "endDate": _d(-1)},
    )
    assert resp.status_code == 200
    data = resp.json()
    # -2、-1 手工跳过，仅 -3 新增
    assert data["synced"] == 1
    assert data["skipped"] == 2

    # 手工行未被覆盖：-2 温度仍是 9.9、无光照；-1 光照未写入
    resp = await client.get(
        f"/projects/{wx_project}/weather?startDate={_d(-2)}&endDate={_d(0)}"
    )
    items = {w["date"]: w for w in resp.json()["items"]}
    assert items[_d(-2)]["temperatureC"] == 9.9
    assert items[_d(-2)]["sunshineHours"] is None
    assert items[_d(-2)]["isSynced"] is False
    assert items[_d(-1)]["isSynced"] is False

    # -3 同步写入可见
    resp = await client.get(
        f"/projects/{wx_project}/weather?startDate={_d(-3)}&endDate={_d(-2)}"
    )
    item = resp.json()["items"][0]
    assert item["date"] == _d(-3)
    assert item["isSynced"] is True
    assert item["sunshineHours"] == 2.5


async def test_sync_update_existing_synced_row(
    client: AsyncClient, wx_project, monkeypatch
):
    """已同步行再次同步有数值差异 → 更新并计数。"""
    await _set_coords(client, wx_project)

    async def fake_fetch_v1(lat, lon, start, end, **kwargs):
        return [_pt(-1, 3.2, 0.5, 2.5)]

    monkeypatch.setattr(weather_sync_module, "fetch_archive_daily", fake_fetch_v1)
    resp = await client.post(
        f"/projects/{wx_project}/weather/sync",
        json={"startDate": _d(-1), "endDate": _d(-1)},
    )
    assert resp.json()["synced"] == 1

    async def fake_fetch_v2(lat, lon, start, end, **kwargs):
        return [_pt(-1, 4.4, 0.5, 2.5)]

    monkeypatch.setattr(weather_sync_module, "fetch_archive_daily", fake_fetch_v2)
    resp = await client.post(
        f"/projects/{wx_project}/weather/sync",
        json={"startDate": _d(-1), "endDate": _d(-1)},
    )
    assert resp.json()["synced"] == 1

    resp = await client.get(
        f"/projects/{wx_project}/weather?startDate={_d(-1)}&endDate={_d(0)}"
    )
    item = resp.json()["items"][0]
    assert item["temperatureC"] == 4.4


async def test_sync_default_window_from_project_dates(
    client: AsyncClient, wx_project, monkeypatch
):
    """省略窗口时：默认 earliest（actual/planned start）→ 今天。"""
    await _set_coords(client, wx_project)
    captured: dict = {}

    async def fake_fetch(lat, lon, start, end, **kwargs):
        captured["start"] = start
        captured["end"] = end
        return []

    monkeypatch.setattr(weather_sync_module, "fetch_archive_daily", fake_fetch)
    resp = await client.post(f"/projects/{wx_project}/weather/sync", json={})
    assert resp.status_code == 200
    assert captured["start"] == _TODAY - dt.timedelta(days=30)
    assert captured["end"] == _TODAY
    assert resp.json()["synced"] == 0
