"""数据体检：标签/切片配置体检端点测试。

只读提示同一图表内不同切片标签重叠（饼图会重复计入）。
"""

# pyright: reportCallIssue=false
from typing import cast

import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.chart import ChartDefinition
from src.models.project import Project
from src.models.slice import ChartSlice, SliceTagMapping
from src.models.tag import Tag


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(name="诊断标签项目", is_active=True)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _mk_slice(
    db_session: AsyncSession,
    project: Project,
    chart_id: int,
    name: str,
    sort_order: int,
    tag_ids: list[tuple[int, int]],
) -> None:
    pid = cast(int, project.id)
    s = ChartSlice(project_id=pid, chart_id=chart_id, name=name, sort_order=sort_order)
    db_session.add(s)
    await db_session.flush()
    db_session.add_all(
        SliceTagMapping(slice_id=cast(int, s.id), tag_id=tid, tag_group=grp)
        for tid, grp in tag_ids
    )
    await db_session.commit()


async def test_no_overlap_returns_empty(client: AsyncClient, project: Project):
    resp = await client.get(f"/projects/{project.id}/diagnostics/tag-chart")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_overlap_slices_detected(
    client: AsyncClient, db_session: AsyncSession, project: Project
):
    pid = cast(int, project.id)
    t1 = Tag(project_id=pid, name="施工用材", group="材料", description="d")
    t2 = Tag(project_id=pid, name="地下工程", group="部位", description="d")
    db_session.add_all([t1, t2])
    await db_session.commit()
    await db_session.refresh(t1)
    await db_session.refresh(t2)

    chart = ChartDefinition(project_id=pid, name="重叠图", description="d")
    db_session.add(chart)
    await db_session.commit()
    await db_session.refresh(chart)
    cid = cast(int, chart.id)

    # slice A：施工用材 + 地下工程（同组且）；slice B：地下工程 —— 覆盖重叠
    await _mk_slice(
        db_session, project, cid, "A", 0, [(cast(int, t1.id), 0), (cast(int, t2.id), 0)]
    )
    await _mk_slice(db_session, project, cid, "B", 1, [(cast(int, t2.id), 0)])

    resp = await client.get(f"/projects/{pid}/diagnostics/tag-chart")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "OVERLAP_SLICES"
    assert items[0]["chartName"] == "重叠图"
    assert set(items[0]["sliceNames"]) == {"A", "B"}
    assert "地下工程" in items[0]["overlapTags"]


async def test_builtin_category_overlap_detected(
    client: AsyncClient, db_session: AsyncSession, project: Project
):
    """内置分类切片（材料）与普通标签（材料-商品砼）也可报告重叠。"""
    pid = cast(int, project.id)
    t1 = Tag(project_id=pid, name="商品混凝土", group="材料", description="d")
    db_session.add(t1)
    await db_session.commit()
    await db_session.refresh(t1)

    chart = ChartDefinition(project_id=pid, name="材料图", description="d")
    db_session.add(chart)
    await db_session.commit()
    await db_session.refresh(chart)
    cid = cast(int, chart.id)
    await _mk_slice(db_session, project, cid, "全部材料", 0, [(-3, 0)])  # 内置 材料
    await _mk_slice(db_session, project, cid, "商砼", 1, [(cast(int, t1.id), 0)])

    resp = await client.get(f"/projects/{pid}/diagnostics/tag-chart")
    items = resp.json()["items"]
    # 覆盖集“材料”与“商品混凝土”不相交 → 不误报
    assert items == []


async def test_overlap_ignores_cross_chart(
    client: AsyncClient, db_session: AsyncSession, project: Project
):
    """跨图表同标签不提示（每个图表独立判定）。"""
    pid = cast(int, project.id)
    t1 = Tag(project_id=pid, name="施工用材", group="材料", description="d")
    db_session.add(t1)
    await db_session.commit()
    await db_session.refresh(t1)
    tid = cast(int, t1.id)

    for i in range(2):
        chart = ChartDefinition(project_id=pid, name=f"图{i}", description="d")
        db_session.add(chart)
        await db_session.commit()
        await db_session.refresh(chart)
        await _mk_slice(db_session, project, cast(int, chart.id), "A", 0, [(tid, 0)])

    resp = await client.get(f"/projects/{pid}/diagnostics/tag-chart")
    assert resp.json()["items"] == []
