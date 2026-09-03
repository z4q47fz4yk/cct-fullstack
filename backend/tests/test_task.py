# pyright: reportCallIssue=false
from urllib.parse import parse_qs

import pytest
import pytest_asyncio
from faker import Faker
from httpx2 import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tag import Tag, TagDimension, TaskTag
from src.models.task import Task, TaskDependency
from src.schemas.task import DependencyType

# 默认项目 id（由 alembic 迁移 10f6fdbf450e seed）
PID = 1


@pytest_asyncio.fixture
async def tasks(db_session: AsyncSession):
    """创建测试任务数据"""
    fake = Faker("zh_CN")
    tasks = [
        Task(
            id=i + 1,
            project_id=PID,
            code=f"TC-{i + 1:03d}",
            name=fake.word(),
            description=fake.sentence(),
            duration=fake.random_int(min=1, max=10),
            completed=0.0,
        )
        for i in range(5)
    ]

    db_session.add_all(tasks)
    await db_session.commit()
    return tasks


@pytest_asyncio.fixture
async def tasks_with_deps(db_session: AsyncSession):
    """创建带依赖关系的测试任务数据

    创建以下依赖结构:
    Task1 -> Task2 -> Task4
    Task3 -> Task4
    Task5 (独立)
    """
    fake = Faker("zh_CN")
    tasks = [
        Task(
            id=i + 1,
            project_id=PID,
            code=f"TC-{i + 1:03d}",
            name=fake.word(),
            description=fake.sentence(),
            duration=5.0 if i < 3 else 3.0,
            completed=0.0,
        )
        for i in range(5)
    ]

    db_session.add_all(tasks)
    await db_session.commit()

    # 创建依赖关系
    # Task2 依赖 Task1
    dep1 = TaskDependency(
        task_id=2, predecessor_id=1, type=DependencyType.FS, project_id=PID
    )
    # Task4 依赖 Task2
    dep2 = TaskDependency(
        task_id=4, predecessor_id=2, type=DependencyType.FS, project_id=PID
    )
    # Task4 依赖 Task3
    dep3 = TaskDependency(
        task_id=4, predecessor_id=3, type=DependencyType.FS, project_id=PID
    )

    db_session.add_all([dep1, dep2, dep3])
    await db_session.commit()

    return tasks


# =============================================================================
# 任务 CRUD 测试
# =============================================================================


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("", id="all"),
        pytest.param("page=1", id="pagination1"),
        pytest.param("page=2&per_page=2", id="pagination2"),
        pytest.param("page=4&per_page=3", id="pagination3"),
        pytest.param("name=任务", id="filter_by_name1"),
        pytest.param("name=nonexistent", id="filter_by_name2"),
    ],
)
async def test_list_tasks(tasks, client: AsyncClient, query: str):
    def calc_expected(q: str, r: list[Task]) -> tuple[int, int]:
        params = parse_qs(q.lstrip("?"))

        name = params.get("name", [None])[0]
        page = int(params.get("page", [1])[0])
        per_page = int(params.get("per_page", [20])[0])

        # 筛选
        filtered = r
        if name:
            filtered = [t for t in filtered if name in t.name]

        total = len(filtered)
        offset = (page - 1) * per_page
        items_count = min(per_page, max(0, total - offset))
        return total, items_count

    resp = await client.get(f"/projects/{PID}/task?{query}")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data

    expected_total, expected_length = calc_expected(query, tasks)
    assert data["total"] == expected_total
    assert len(data["items"]) == expected_length


@pytest.mark.parametrize("t_id", [pytest.param(1), pytest.param(2), pytest.param(999)])
async def test_get_task(tasks, t_id: int, client: AsyncClient):
    resp = await client.get(f"/projects/{PID}/task/{t_id}")
    exists = bool([t.id for t in tasks if t.id == t_id])
    assert resp.status_code == 200 if exists else 404
    if exists:
        data = resp.json()
        assert "id" in data
        assert "code" in data
        assert "name" in data
        assert "duration" in data
        assert "completed" in data
        assert "createdAt" in data
        assert "updatedAt" in data


@pytest.mark.parametrize(
    "payload, code",
    [
        pytest.param({}, 422, id="invalid_payload_empty"),
        pytest.param({"name": "test"}, 422, id="missing_duration"),
        pytest.param({"duration": 5.0}, 422, id="missing_name"),
        pytest.param(
            {"name": "", "duration": 5.0},
            422,
            id="empty_name",
        ),
        pytest.param(
            {"name": "d" * 101, "duration": 5.0},
            422,
            id="too_long_name",
        ),
        pytest.param(
            {"name": "test", "duration": 0.3},
            422,
            id="duration_too_small",
        ),
        pytest.param(
            {"name": "test", "duration": 5.0, "completed": 1.5},
            422,
            id="completed_out_of_range",
        ),
        pytest.param(
            {"name": "test", "duration": 5.0, "code": "AUTO-123"},
            422,
            id="invalid_auto_prefix_code",
        ),
        pytest.param(
            {"name": "test", "duration": 5.0, "code": "auto-test"},
            422,
            id="invalid_auto_lowercase_prefix_code",
        ),
        pytest.param(
            {"name": "test", "duration": 5.0},
            201,
            id="minimal",
        ),
        pytest.param(
            {"name": "test", "duration": 5.0, "description": "desc"},
            201,
            id="with_description",
        ),
        pytest.param(
            {"name": "test", "duration": 5.0, "predecessor_ids": [1]},
            201,
            id="with_predecessor",
        ),
        pytest.param(
            {"name": "test", "duration": 5.0, "predecessor_ids": [999]},
            404,
            id="with_nonexistent_predecessor",
        ),
    ],
)
async def test_create_task(tasks, client: AsyncClient, payload: dict, code: int):
    resp = await client.post(f"/projects/{PID}/task", json=payload)
    assert resp.status_code == code
    if resp.status_code == 201:
        data = resp.json()
        assert "id" in data
        assert "code" in data
        assert "createdAt" in data
        assert "updatedAt" in data
        # 验证自动编码生成
        if "code" not in payload:
            assert data["code"].startswith("AUTO-")
        # 验证前置依赖创建
        if payload.get("predecessor_ids") and code == 201:
            # 查询依赖关系
            deps_resp = await client.get(
                f"/projects/{PID}/task/{data['id']}/predecessors"
            )
            assert deps_resp.status_code == 200
            deps = deps_resp.json()
            assert len(deps) == len(payload["predecessor_ids"])


@pytest.mark.parametrize(
    "t_id, payload, code",
    [
        pytest.param(1, {}, 200, id="empty_payload"),
        pytest.param(0, {}, 404, id="invalid_id"),
        pytest.param(999, {"name": "test"}, 404, id="nonexistent_id"),
        pytest.param(1, {"name": "updated"}, 200, id="partial_update_name"),
        pytest.param(1, {"description": "updated"}, 200, id="partial_update_desc"),
        pytest.param(1, {"duration": 11.0}, 200, id="partial_update_duration"),
        pytest.param(1, {"completed": 0.5}, 200, id="partial_update_completed"),
        pytest.param(1, {"code": "TC-NEW"}, 200, id="partial_update_code"),
        pytest.param(1, {"code": "AUTO-123"}, 422, id="invalid_auto_prefix_code"),
        pytest.param(
            1, {"name": "updated", "duration": 8.0}, 200, id="multiple_update"
        ),
        pytest.param(1, {"name": "d" * 101}, 422, id="invalid_name"),
        pytest.param(1, {"description": "d" * 501}, 422, id="invalid_description"),
        pytest.param(1, {"duration": 0.3}, 422, id="invalid_duration"),
        pytest.param(1, {"completed": 1.5}, 422, id="invalid_completed"),
    ],
)
async def test_update_task(
    tasks, client: AsyncClient, t_id: int, payload: dict, code: int
):
    # duration 用 11.0 而非 10.0：fixture 的随机 duration 范围是 1..10，
    # 若 payload 落在该范围内（如 10.0），当随机值恰好等于它时，SQLAlchemy
    # 会跳过实际 UPDATE，DB 触发器不触发，updatedAt 与 createdAt 相等，
    # 导致下方 createdAt != updatedAt 断言偶发失败。
    resp = await client.put(f"/projects/{PID}/task/{t_id}", json=payload)
    assert resp.status_code == code
    if resp.status_code == 200:
        data = resp.json()
        assert "id" in data
        assert "createdAt" in data
        assert "updatedAt" in data
        if not payload:
            # payload 为空时，不会触发更新
            return
        for k, v in payload.items():
            # 转换 snake_case 到 camelCase 进行验证
            camel_key = "".join(
                word.capitalize() if i > 0 else word
                for i, word in enumerate(k.split("_"))
            )
            assert camel_key in data
            assert data[camel_key] == v
        # 验证 updatedAt 被更新
        if payload:
            assert data["createdAt"] != data["updatedAt"]


@pytest.mark.parametrize(
    "t_id, code",
    [
        pytest.param(0, 404, id="invalid_id"),
        pytest.param(999, 404, id="nonexistent_id"),
        pytest.param(5, 204, id="success"),
    ],
)
async def test_delete_task(tasks, client: AsyncClient, t_id: int, code: int):
    resp = await client.delete(f"/projects/{PID}/task/{t_id}")
    assert resp.status_code == code


async def test_delete_task_with_dependents(tasks_with_deps, client: AsyncClient):
    """测试删除被依赖的任务返回 409"""
    # Task1 被 Task2 依赖
    resp = await client.delete(f"/projects/{PID}/task/1")
    assert resp.status_code == 409


# =============================================================================
# 依赖关系测试
# =============================================================================


async def test_get_predecessors(tasks_with_deps, client: AsyncClient):
    """测试获取前置依赖列表"""
    # Task2 有前置依赖 Task1
    resp = await client.get(f"/projects/{PID}/task/2/predecessors")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["code"] == "TC-001"
    assert "name" in data[0]
    assert "type" in data[0]

    # Task4 有两个前置依赖
    resp = await client.get(f"/projects/{PID}/task/4/predecessors")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    pred_ids = [d["id"] for d in data]
    assert 2 in pred_ids
    assert 3 in pred_ids

    # Task1 没有前置依赖
    resp = await client.get(f"/projects/{PID}/task/1/predecessors")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 0


async def test_get_predecessors_nonexistent_task(client: AsyncClient):
    """测试获取不存在任务的前置依赖"""
    resp = await client.get(f"/projects/{PID}/task/999/predecessors")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "t_id, payload, code",
    [
        pytest.param(
            3,
            {"predecessor_id": 1},
            201,
            id="success",
        ),
        pytest.param(
            999,
            {"predecessor_id": 1},
            404,
            id="nonexistent_task",
        ),
        pytest.param(
            1,
            {"predecessor_id": 999},
            404,
            id="nonexistent_predecessor",
        ),
        pytest.param(
            1,
            {"predecessor_id": 1},
            422,
            id="self_reference",
        ),
        pytest.param(
            2,
            {"predecessor_id": 1},
            409,
            id="duplicate",
        ),
        pytest.param(
            4,
            {"predecessor_id": 1},
            201,
            id="multi_successor",
        ),
        pytest.param(
            1,
            {"predecessor_id": 4},
            422,
            id="cycle_dependency_reverse",
        ),
    ],
)
async def test_add_predecessor(
    tasks_with_deps, client: AsyncClient, t_id: int, payload: dict, code: int
):
    """测试添加前置依赖"""
    resp = await client.post(f"/projects/{PID}/task/{t_id}/predecessors", json=payload)
    assert resp.status_code == code
    if resp.status_code == 201:
        data = resp.json()
        assert "id" in data
        assert "code" in data
        assert "name" in data
        assert "type" in data


async def test_add_predecessor_with_type(tasks, client: AsyncClient):
    """测试添加带依赖类型的前置依赖"""
    payload = {"predecessor_id": 1, "type": "SS"}
    resp = await client.post(f"/projects/{PID}/task/2/predecessors", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "SS"


@pytest.mark.parametrize(
    "t_id, pred_id, code",
    [
        pytest.param(2, 1, 204, id="success"),
        pytest.param(2, 999, 404, id="nonexistent_predecessor"),
        pytest.param(999, 1, 404, id="nonexistent_task"),
        pytest.param(1, 2, 404, id="not_a_predecessor"),
    ],
)
async def test_remove_predecessor(
    tasks_with_deps, client: AsyncClient, t_id: int, pred_id: int, code: int
):
    """测试删除前置依赖"""
    resp = await client.delete(f"/projects/{PID}/task/{t_id}/predecessors/{pred_id}")
    assert resp.status_code == code

    if resp.status_code == 204:
        # 验证依赖已删除
        deps_resp = await client.get(f"/projects/{PID}/task/{t_id}/predecessors")
        deps = deps_resp.json()
        assert pred_id not in [d["id"] for d in deps]


@pytest.mark.parametrize(
    "t_id, pred_id, payload, expected",
    [
        pytest.param(2, 1, {"type": "SS"}, {"type": "SS"}, id="type_only"),
        pytest.param(2, 1, {"type": "FF"}, {"type": "FF"}, id="type_change"),
        pytest.param(4, 2, {}, {"type": "FS"}, id="empty_payload"),
    ],
)
async def test_update_predecessor(
    tasks_with_deps,
    client: AsyncClient,
    t_id: int,
    pred_id: int,
    payload: dict,
    expected: dict,
):
    """测试更新前置依赖的 type"""
    resp = await client.put(
        f"/projects/{PID}/task/{t_id}/predecessors/{pred_id}", json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == pred_id
    assert data["type"] == expected["type"]

    # 验证 GET 结果与更新一致
    deps_resp = await client.get(f"/projects/{PID}/task/{t_id}/predecessors")
    assert deps_resp.status_code == 200
    deps = {d["id"]: d for d in deps_resp.json()}
    assert deps[pred_id]["type"] == expected["type"]


@pytest.mark.parametrize(
    "t_id, pred_id, payload",
    [
        pytest.param(2, 999, {"type": "SS"}, id="nonexistent_predecessor"),
        pytest.param(999, 1, {"type": "SS"}, id="nonexistent_task"),
        pytest.param(1, 2, {"type": "SS"}, id="not_a_predecessor"),
    ],
)
async def test_update_predecessor_not_found(
    tasks_with_deps, client: AsyncClient, t_id: int, pred_id: int, payload: dict
):
    """测试更新不存在的依赖返回 404"""
    resp = await client.put(
        f"/projects/{PID}/task/{t_id}/predecessors/{pred_id}", json=payload
    )
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"type": None}, id="null_type"),
    ],
)
async def test_update_predecessor_explicit_null(
    tasks_with_deps, client: AsyncClient, payload: dict
):
    """测试显式传 null 更新 NOT NULL 字段返回 422"""
    resp = await client.put(f"/projects/{PID}/task/2/predecessors/1", json=payload)
    assert resp.status_code == 422


async def test_get_available_predecessors(tasks_with_deps, client: AsyncClient):
    """测试获取可选前置任务列表"""
    # 为 Task4 获取可选前置任务
    resp = await client.get(f"/projects/{PID}/task/4/available-predecessors")
    assert resp.status_code == 200
    data = resp.json()

    # 应该返回 TaskSummary 列表
    assert isinstance(data, list)

    # 验证字段
    if data:
        assert "id" in data[0]
        assert "code" in data[0]
        assert "name" in data[0]
        assert "duration" in data[0]

    # 可选列表中不应该包含自身
    ids = [t["id"] for t in data]
    assert 4 not in ids

    # 可选列表中不应该包含已存在的前置任务
    assert 2 not in ids
    assert 3 not in ids

    # 可选列表中不应该包含会形成循环的任务 (Task4 的后继任务)
    # 在当前结构中 Task4 没有后继任务，所以不需要检查


async def test_get_available_predecessors_excludes_cycle(
    tasks_with_deps, client: AsyncClient
):
    """测试可选前置任务排除会形成循环的任务"""
    # Task1 是 Task2 的前置，Task2 是 Task4 的前置
    # 所以 Task4 是 Task1 的后继，添加 Task4 作为 Task1 的前置会形成循环
    resp = await client.get(f"/projects/{PID}/task/1/available-predecessors")
    assert resp.status_code == 200
    data = resp.json()

    ids = [t["id"] for t in data]
    # Task4 不应该在可选列表中，因为会形成循环
    assert 4 not in ids


async def test_get_available_predecessors_nonexistent_task(client: AsyncClient):
    """测试获取不存在任务的可选前置列表"""
    resp = await client.get(f"/projects/{PID}/task/999/available-predecessors")
    assert resp.status_code == 404


# =============================================================================
# 统计信息测试
# =============================================================================


async def test_get_schedule_stats_empty(client: AsyncClient):
    """测试空任务的统计信息"""
    resp = await client.get(f"/projects/{PID}/task/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert "totalTasks" in data
    assert "totalDuration" in data
    assert "criticalDuration" in data

    assert data["totalTasks"] == 0
    assert data["totalDuration"] == 0.0
    assert data["criticalDuration"] == 0.0


async def test_get_schedule_stats(tasks_with_deps, client: AsyncClient):
    """测试获取进度统计信息"""
    resp = await client.get(f"/projects/{PID}/task/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert "totalTasks" in data
    assert "totalDuration" in data
    assert "criticalDuration" in data

    # 验证统计值
    assert data["totalTasks"] == 5
    # 总工期 = 5 + 5 + 5 + 3 + 3 = 21
    assert data["totalDuration"] == 21.0

    # 关键路径工期应该小于等于总工期
    assert data["criticalDuration"] <= data["totalDuration"]
    # 关键路径工期应该大于0
    assert data["criticalDuration"] > 0


async def test_get_schedule_stats_with_critical_path(
    tasks_with_deps, client: AsyncClient
):
    """测试关键路径计算正确性"""
    resp = await client.get(f"/projects/{PID}/task/stats")
    data = resp.json()

    # 任务结构:
    # Task1 (5天) -> Task2 (5天) -> Task4 (3天)
    # Task3 (5天) -------------> Task4 (3天)
    # Task5 (3天) (独立)

    # 关键路径应该是 Task1 -> Task2 -> Task4 = 13天
    # 或者 Task3 -> Task4 = 8天
    # 所以关键路径工期是 13天
    assert data["criticalDuration"] == 13.0


# =============================================================================
# 任务列表携带直接标签（include_tags 开关）
# =============================================================================


@pytest_asyncio.fixture
async def tagged_tasks(db_session: AsyncSession):
    """三个命名唯一的任务（tagtest-*），并挂载标签。"""
    tasks = [
        Task(
            id=1001 + i,
            project_id=PID,
            code=f"TAGT-{i + 1:03d}",
            name=f"tagtest-task{i + 1}",
            description="d",
            duration=5.0,
            completed=0.0,
        )
        for i in range(3)
    ]
    db_session.add_all(tasks)
    await db_session.commit()
    for t in tasks:
        await db_session.refresh(t)

    dim = TagDimension(project_id=PID, name="任务测试维度", description="d")
    db_session.add(dim)
    await db_session.commit()
    await db_session.refresh(dim)
    assert dim.id is not None

    tag_a = Tag(project_id=PID, dimension_id=dim.id, name="tagtest-A", description="d")
    tag_b = Tag(project_id=PID, dimension_id=dim.id, name="tagtest-B", description="d")
    db_session.add_all([tag_a, tag_b])
    await db_session.commit()
    await db_session.refresh(tag_a)
    await db_session.refresh(tag_b)

    assert dim.id is not None and tag_a.id is not None and tag_b.id is not None
    assert (
        tasks[0].id is not None and tasks[1].id is not None and tasks[2].id is not None
    )

    # task1 → tag_b（乱序写入验证按 id 升序）、tag_a；task2 → tag_a；task3 无标签
    db_session.add_all([
        TaskTag(project_id=PID, task_id=tasks[0].id, tag_id=tag_b.id),
        TaskTag(project_id=PID, task_id=tasks[0].id, tag_id=tag_a.id),
        TaskTag(project_id=PID, task_id=tasks[1].id, tag_id=tag_a.id),
    ])
    await db_session.commit()
    return tasks


async def test_list_tasks_tags_empty_by_default(client: AsyncClient, tagged_tasks):
    """默认不带 include_tags 时，每个任务返回空 tags 列表。"""
    resp = await client.get(f"/projects/{PID}/task?name=tagtest&per_page=100")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {it["name"] for it in items} == {
        "tagtest-task1",
        "tagtest-task2",
        "tagtest-task3",
    }
    assert all(it["tags"] == [] for it in items)


async def test_list_tasks_include_tags(client: AsyncClient, tagged_tasks):
    """include_tags=true 时返回直接标签（按 ID 升序），无标签任务返回空数组。"""
    resp = await client.get(
        f"/projects/{PID}/task?name=tagtest&include_tags=true&per_page=100"
    )
    assert resp.status_code == 200
    by_name = {it["name"]: it for it in resp.json()["items"]}

    assert [t["name"] for t in by_name["tagtest-task1"]["tags"]] == [
        "tagtest-A",
        "tagtest-B",
    ]
    assert [t["name"] for t in by_name["tagtest-task2"]["tags"]] == ["tagtest-A"]
    assert by_name["tagtest-task3"]["tags"] == []


async def test_list_tasks_include_tags_pagination(client: AsyncClient, tagged_tasks):
    """分页只加载当前页任务的标签，跨页不串数据。"""
    resp = await client.get(
        f"/projects/{PID}/task?name=tagtest&include_tags=true&per_page=1&page=2"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "tagtest-task2"
    assert [t["name"] for t in items[0]["tags"]] == ["tagtest-A"]


async def test_list_tasks_include_tags_project_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
    tagged_tasks,
):
    """其他项目挂同名标签的任务不串入本项目列表。"""
    from src.models.project import Project

    other_project = Project(name="任务标签隔离项目", is_active=True)
    db_session.add(other_project)
    await db_session.commit()
    await db_session.refresh(other_project)
    assert other_project.id is not None

    other = Task(
        project_id=other_project.id,
        code="TAGT-OTHER",
        name="tagtest-other",
        description="d",
        duration=5.0,
        completed=0.0,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    assert other.id is not None

    other_dim = TagDimension(
        project_id=other_project.id, name="其他项目维度", description="d"
    )
    db_session.add(other_dim)
    await db_session.commit()
    await db_session.refresh(other_dim)
    assert other_dim.id is not None
    other_tag = Tag(
        project_id=other_project.id,
        dimension_id=other_dim.id,
        name="tagtest-A",
        description="d",
    )
    db_session.add(other_tag)
    await db_session.commit()
    await db_session.refresh(other_tag)
    assert other_tag.id is not None
    db_session.add(
        TaskTag(project_id=other_project.id, task_id=other.id, tag_id=other_tag.id)
    )
    await db_session.commit()

    resp = await client.get(
        f"/projects/{PID}/task?name=tagtest&include_tags=true&per_page=100"
    )
    assert resp.status_code == 200
    by_name = {it["name"]: it for it in resp.json()["items"]}
    assert "tagtest-other" not in by_name
    assert [t["name"] for t in by_name["tagtest-task1"]["tags"]] == [
        "tagtest-A",
        "tagtest-B",
    ]
    assert [t["name"] for t in by_name["tagtest-task2"]["tags"]] == ["tagtest-A"]
    assert by_name["tagtest-task3"]["tags"] == []
