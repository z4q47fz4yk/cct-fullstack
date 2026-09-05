# Tests

pytest + pytest-asyncio suite. Nested transactions for isolation (rollback after each test). Flat structure — no unit/integration split.

## Commands

```bash
.venv/bin/pytest                                    # all tests
.venv/bin/pytest tests/test_task.py                 # single file
.venv/bin/pytest tests/test_task.py::test_create_task  # single function
.venv/bin/pytest -k "resource"                      # pattern match
.venv/bin/pytest --cov=src --cov-report=term-missing   # coverage
.venv/bin/pytest -x                                 # stop on first failure
```

## Fixtures (conftest.py)

- `db_engine` — async engine to `cctv2-test`, NullPool, module-scoped
- `db_session` — nested transaction per test, function-scoped, rollback on teardown
- `client` — httpx2 `AsyncClient` with `get_session` dependency override

## Test Files

| File                          | Tests | Parametrized Cases | What It Covers                                         |
| ----------------------------- | ----- | ------------------ | ------------------------------------------------------ |
| `test_task.py`                | 15    | ~47                | CRUD, predecessors, cycle detection, schedule stats    |
| `test_resourcev2.py`          | 5     | ~36                | CRUD, filters (name/category/pagination)               |
| `test_resource_usage.py`      | 16    | ~30                | Batch create, CRUD, filters, FK/unique violations      |
| `test_daily_report.py`        | 5     | ~16                | 4-step import pipeline, CSV parsing, error cases       |
| `test_daily_report_parser.py` | 8     | 8                  | Unit tests against real CSV (docs/20251214.csv)        |
| `test_project.py`             | 5     | ~30                | CRUD, land_area/building_area fields                   |
| `test_optimize.py`            | 8     | ~30                | Run CRUD, constraint CRUD, status-dependent responses  |
| `test_resource_public.py`     | 10    | ~15                | Read-only list, batch copy (by IDs, by category)       |
| `test_carbon_stats.py`        | 14    | 14                 | Carbon stats endpoint (ACTUAL/PLANNED filtering, day/week/month granularity, date windows, usage-only) |
| `test_db_errors.py`           | 8     | 8                  | Unit tests for SQLSTATE violation detection utilities  |

## Conventions

- Tests that need project-scoped data must create `Project` rows (default id=1 from migration)
- `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio`
- Parametrized tests use `@pytest.mark.parametrize` extensively
- Test DB: `postgresql://cct:cct@localhost/cctv2-test` — must run `alembic upgrade head` first（asyncpg 驱动由 `settings.database_async_url` 注入）
- Fixture data uses deterministic IDs (not UUIDs) for easy assertions
