"""日报运输块（A2）：货物类别解析、导入打标、导入后可改标。"""
# pyright: reportCallIssue=false

from typing import cast

import pytest_asyncio
from httpx2 import AsyncClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.resource import Resource, ResourceCategory
from src.models.tag import Tag, TagDimension, UsageTag
from src.models.task import Task

# 默认项目 id
PID = 1
USAGE_DATE = "2026-06-28"


def _build_transport_csv_bytes() -> bytes:
    """含运输块的 CSV：两列两辆车，货物类别分别为 渣土 / 建材。"""
    lines = [
        "section,col1,col2",
        "货物类别,渣土,建材",
        "运输工具,重型卡车A,重型卡车B",
        "车次,2,3",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


@pytest_asyncio.fixture
async def transport_tags(db_session: AsyncSession) -> dict[str, Tag | TagDimension]:
    """「运输货物」维度：材料运输 → [渣土, 建材]。"""
    dim = TagDimension(project_id=PID, name="运输货物", description="d")
    db_session.add(dim)
    await db_session.commit()
    await db_session.refresh(dim)
    root = Tag(
        project_id=PID, dimension_id=cast(int, dim.id), name="材料运输", description="d"
    )
    db_session.add(root)
    await db_session.commit()
    await db_session.refresh(root)
    leaf_a = Tag(
        project_id=PID,
        dimension_id=cast(int, dim.id),
        name="渣土",
        parent_id=cast(int, root.id),
        description="d",
    )
    leaf_b = Tag(
        project_id=PID,
        dimension_id=cast(int, dim.id),
        name="建材",
        parent_id=cast(int, root.id),
        description="d",
    )
    db_session.add_all([leaf_a, leaf_b])
    await db_session.commit()
    await db_session.refresh(leaf_a)
    await db_session.refresh(leaf_b)
    return {"dim": dim, "root": root, "渣土": leaf_a, "建材": leaf_b}


@pytest_asyncio.fixture
async def transport_tasks(db_session: AsyncSession):
    objs = [
        Task(
            id=30001,
            project_id=PID,
            code="TR-T1",
            name="TR-T1",
            duration=5.0,
            completed=0.0,
        ),
        Task(
            id=30002,
            project_id=PID,
            code="TR-T2",
            name="TR-T2",
            duration=5.0,
            completed=0.0,
        ),
    ]
    db_session.add_all(objs)
    await db_session.commit()
    return objs


async def _parse_transport(client: AsyncClient) -> str:
    resp = await client.post(
        f"/projects/{PID}/daily-report/parse",
        files={"file": ("transport.csv", _build_transport_csv_bytes(), "text/csv")},
        data={"usage_date": USAGE_DATE},
    )
    assert resp.status_code == 200, f"parse failed: {resp.text}"
    return resp.json()["batchId"]


async def test_transport_parse_carries_cargo(client: AsyncClient):
    """解析结果携带 cargo 字段。"""
    resp = await client.post(
        f"/projects/{PID}/daily-report/parse",
        files={"file": ("transport.csv", _build_transport_csv_bytes(), "text/csv")},
        data={"usage_date": USAGE_DATE},
    )
    assert resp.status_code == 200
    items = resp.json()["parsedItems"]
    by_name = {it["resourceName"]: it for it in items}
    assert by_name["重型卡车A"]["cargo"] == "渣土"
    assert by_name["重型卡车B"]["cargo"] == "建材"
    assert {it["category"] for it in items} == {"transport"}


async def test_transport_full_flow_tags_usage(
    client: AsyncClient,
    db_session: AsyncSession,
    transport_tags,
    transport_tasks,
):
    """完整流程：parse → confirm(cargo) → allocate(cargo) → submit 自动打标。"""
    batch_id = await _parse_transport(client)

    resp = await client.post(
        f"/projects/{PID}/daily-report/batches/{batch_id}/confirm-mapping",
        json=[
            {
                "resourceName": "重型卡车A",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "重型卡车A",
                    "description": "d",
                    "category": "transport",
                    "carbonFactor": 4.0,
                },
                "quantity": 2,
                "cargo": "渣土",
            },
            {
                "resourceName": "重型卡车B",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "重型卡车B",
                    "description": "d",
                    "category": "transport",
                    "carbonFactor": 5.0,
                },
                "quantity": 3,
                "cargo": "建材",
            },
        ],
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"/projects/{PID}/daily-report/batches/{batch_id}/allocate",
        json=[
            {
                "resourceName": "重型卡车A",
                "taskId": 30001,
                "quantity": 2,
                "cargo": "渣土",
            },
            {
                "resourceName": "重型卡车B",
                "taskId": 30002,
                "quantity": 3,
                "cargo": "建材",
            },
        ],
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(f"/projects/{PID}/daily-report/batches/{batch_id}/submit")
    assert resp.status_code == 200, resp.text
    usage_ids = resp.json()["taskResourceUsageIds"]
    assert len(usage_ids) == 2

    # 用量已被自动打上货物类别标签
    tags = (
        await db_session.exec(
            select(UsageTag)
            .where(
                UsageTag.project_id == PID,
                col(UsageTag.usage_id).in_(usage_ids),
            )
            .order_by(col(UsageTag.usage_id))
        )
    ).all()
    tag_ids = {t.tag_id for t in tags}
    assert tag_ids == {transport_tags["渣土"].id, transport_tags["建材"].id}


async def test_transport_confirm_missing_cargo_400(client: AsyncClient):
    """confirm 时 cargo 与解析结果不一致 → 400。"""
    batch_id = await _parse_transport(client)
    resp = await client.post(
        f"/projects/{PID}/daily-report/batches/{batch_id}/confirm-mapping",
        json=[
            {
                "resourceName": "重型卡车A",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "重型卡车A",
                    "description": "d",
                    "category": "transport",
                },
                "quantity": 2,
                "cargo": "生活垃圾",
            },
        ],
    )
    assert resp.status_code == 400
    assert "货物类别" in resp.json()["detail"]


def _make_transport_csv(same_vehicle: bool) -> bytes:
    """构造运输 CSV：可选让两行使用同一车辆名（不同货物类别）。"""
    name_a = "重型卡车A"
    name_b = name_a if same_vehicle else "重型卡车B"
    lines = [
        "section,col1,col2",
        "货物类别,渣土,建材",
        f"运输工具,{name_a},{name_b}",
        "车次,2,3",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


async def test_transport_duplicate_create_new_400(
    client: AsyncClient, db_session: AsyncSession
):
    """同一车辆名两种货物、两条 CREATE_NEW → confirm 400，避免 UNIQUE 冲突。"""
    resp = await client.post(
        f"/projects/{PID}/daily-report/parse",
        files={"file": ("t.csv", _make_transport_csv(same_vehicle=True), "text/csv")},
        data={"usage_date": USAGE_DATE},
    )
    assert resp.status_code == 200
    batch_id = resp.json()["batchId"]
    items = resp.json()["parsedItems"]
    assert len(items) == 2  # 同名不同货物均保留

    resp = await client.post(
        f"/projects/{PID}/daily-report/batches/{batch_id}/confirm-mapping",
        json=[
            {
                "resourceName": "重型卡车A",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "重型卡车A",
                    "description": "d",
                    "category": "transport",
                },
                "quantity": 2,
                "cargo": "渣土",
            },
            {
                "resourceName": "重型卡车A",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "重型卡车A",
                    "description": "d",
                    "category": "transport",
                },
                "quantity": 3,
                "cargo": "建材",
            },
        ],
    )
    assert resp.status_code == 400
    assert "重复创建" in resp.json()["detail"]


async def test_transport_same_vehicle_multi_cargo_use_existing(
    client: AsyncClient,
    db_session: AsyncSession,
    transport_tags,
    transport_tasks,
):
    """同一车辆两种货物、预建资源后 USE_EXISTING → 全流程成功且各自打标。"""
    truck = Resource(
        project_id=PID,
        name="重型卡车A",
        description="d",
        category=ResourceCategory.transport,
        carbon_factor=4.0,
    )
    db_session.add(truck)
    await db_session.commit()
    await db_session.refresh(truck)
    truck_id = truck.id
    assert truck_id is not None

    resp = await client.post(
        f"/projects/{PID}/daily-report/parse",
        files={"file": ("t.csv", _make_transport_csv(same_vehicle=True), "text/csv")},
        data={"usage_date": USAGE_DATE},
    )
    batch_id = resp.json()["batchId"]

    resp = await client.post(
        f"/projects/{PID}/daily-report/batches/{batch_id}/confirm-mapping",
        json=[
            {
                "resourceName": "重型卡车A",
                "action": "USE_EXISTING",
                "quantity": 2,
                "cargo": "渣土",
            },
            {
                "resourceName": "重型卡车A",
                "action": "USE_EXISTING",
                "quantity": 3,
                "cargo": "建材",
            },
        ],
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"/projects/{PID}/daily-report/batches/{batch_id}/allocate",
        json=[
            {
                "resourceName": "重型卡车A",
                "taskId": 30001,
                "quantity": 2,
                "cargo": "渣土",
            },
            {
                "resourceName": "重型卡车A",
                "taskId": 30002,
                "quantity": 3,
                "cargo": "建材",
            },
        ],
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(f"/projects/{PID}/daily-report/batches/{batch_id}/submit")
    assert resp.status_code == 200, resp.text
    usage_ids = resp.json()["taskResourceUsageIds"]
    assert len(usage_ids) == 2

    # 两条用量分属两个任务，各自带正确货物标签
    tags = (
        await db_session.exec(
            select(UsageTag).where(
                UsageTag.project_id == PID,
                col(UsageTag.usage_id).in_(usage_ids),
            )
        )
    ).all()
    assert {t.tag_id for t in tags} == {
        transport_tags["渣土"].id,
        transport_tags["建材"].id,
    }

    # 资源只有一条记录（未被重复创建）
    trucks = (
        await db_session.exec(
            select(Resource).where(
                Resource.project_id == PID, Resource.name == "重型卡车A"
            )
        )
    ).all()
    assert len(trucks) == 1
    assert trucks[0].id == truck_id


async def test_transport_usage_tags_editable_after_import(
    client: AsyncClient,
    db_session: AsyncSession,
    transport_tags,
    transport_tasks,
):
    """导入后仍可通过 PUT /resource-usage/{id}/tags 修改用量标签。"""
    batch_id = await _parse_transport(client)
    await client.post(
        f"/projects/{PID}/daily-report/batches/{batch_id}/confirm-mapping",
        json=[
            {
                "resourceName": "重型卡车A",
                "action": "CREATE_NEW",
                "newResource": {
                    "name": "重型卡车A",
                    "description": "d",
                    "category": "transport",
                },
                "quantity": 2,
                "cargo": "渣土",
            },
        ],
    )
    await client.post(
        f"/projects/{PID}/daily-report/batches/{batch_id}/allocate",
        json=[
            {
                "resourceName": "重型卡车A",
                "taskId": 30001,
                "quantity": 2,
                "cargo": "渣土",
            },
        ],
    )
    resp = await client.post(f"/projects/{PID}/daily-report/batches/{batch_id}/submit")
    usage_id = resp.json()["taskResourceUsageIds"][0]

    resp = await client.get(f"/projects/{PID}/resource-usage/{usage_id}/tags")
    assert resp.status_code == 200
    assert [it["id"] for it in resp.json()] == [transport_tags["渣土"].id]

    # 改标为 建材
    resp = await client.put(
        f"/projects/{PID}/resource-usage/{usage_id}/tags",
        json={"tagIds": [transport_tags["建材"].id]},
    )
    assert resp.status_code == 200
    assert [it["id"] for it in resp.json()] == [transport_tags["建材"].id]
