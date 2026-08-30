# Routers

Thin wrappers that delegate to services. All endpoints async. HTTPException raised here (not in services) with specific status codes.

## Structure

```
routers/
├── project.py          # /project (standalone CRUD, no project_id)
├── task.py             # /projects/{project_id}/task (614 lines, largest)
├── resource.py         # /projects/{project_id}/resource
├── resource_public.py  # Dual: /public-resource + /projects/{project_id}/public-resource
├── resource_usage.py   # /projects/{project_id}/resource-usage
├── daily_report.py     # /projects/{project_id}/daily-report
└── optimize.py         # /projects/{project_id}/optimize
```

## Key Patterns

- **project_filter/project_count_filter** from `src.utils.query` — applied to all list queries on project-scoped models
- **CurrentProject** dependency from URL path — returns `ScopedProject` (id: int)
- **IntegrityError** handling with `is_unique_violation()` / `is_foreign_key_violation()` for 409/422
- **Inline SQLModel error schemas** (`NotFoundResp`, `ConflictResp`, `ErrorResponse`) for OpenAPI docs
- **Endpoint naming**: `{action}_{resource}_endpoint` (suffix stripped by custom OpenAPI ID generator in app.py)
- **Custom `PageParam`** type alias: `tuple[int, int]` (offset, limit)

## Notable Quirks

- `task.py` is 614 lines — complexity hotspot with rich dependency injection (5 service factories via `src/dependencies/task.py`)
- `resource_public.py` uses dual-router pattern: `dict_router` (global) + `copy_router` (project-scoped) merged via `include_router`
- `optimize.py` mixes optimization runs + resource constraints in one file (different tags)
- `optimize.py` uses `get_session` from `src.database` (inconsistent with other routers using `get_db_session`)
- `daily_report.py` is a multi-step workflow: parse → confirm_mapping → allocate → submit
- `project.py` is the only router with no `CurrentProject` dependency
