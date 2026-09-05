# Services

Business logic layer. Receives `AsyncSession` via dependency injection. No repository layer — services handle all data access directly.

## Structure

```
services/
├── task.py                    # Deprecation stub (logic split into 4 specialized services)
├── task_code.py               # TaskCodeService (all staticmethods, generates AUTO-N codes)
├── task_dependency.py         # TaskDependencyService (all staticmethods, graph algorithms)
├── task_scheduler.py          # TaskSchedulerService (critical path calculation)
├── task_assembler.py          # TaskAssembler (all staticmethods, response formatting)
├── daily_report.py            # DailyReportService (multi-step Excel import pipeline)
├── resource_public.py         # ResourcePublicService (global dictionary copy)
├── resource_usage.py          # ResourceUsageService (CRUD for manual submissions)
├── carbon_stats.py           # CarbonStatsService (usage carbon aggregation, usage-only, day/week/month)
├── optimization_adapter.py    # load_optimization_data + OptimizationAdapter (data → NSGA2 types)
├── optimization_consumer.py   # QueueBackedCallback + _event_consumer (async DB writer)
└── public/
    └── pagination.py          # Empty (pagination lives in dependencies)
```

## Service Types

**Stateless** (no constructor, all `@staticmethod`):
- `TaskCodeService` — generates `AUTO-N` codes via PostgreSQL sequence
- `TaskDependencyService` — recursive CTEs for cycle detection, predecessor/successor queries
- `TaskAssembler` — builds camelCase response dicts

**Stateful** (constructor takes `session` + optionally `project_id`):
- `TaskSchedulerService(session)` — wraps `TaskDependencyService`, delegates to `utils/critical_path_method`
- `DailyReportService(session, project_id)` — 4-step pipeline: parse → confirm_mapping → allocate → submit
- `ResourceUsageService(session, project_id)` — CRUD with batch-create support
- `ResourcePublicService(session)` — global dictionary, `project_id` passed per-call for copy
- `CarbonStatsService(session, project_id)` — usage-only carbon aggregation by period (day/week/month) + resource; PLANNED restricted to month granularity

**Async/Special**:
- `optimization_adapter.py` — module-level `load_optimization_data(session, project_id)` loads project data; `OptimizationAdapter` class converts to NSGA2 input types
- `optimization_consumer.py` — `QueueBackedCallback` runs in sync optimizer thread, enqueues events to `asyncio.Queue`; `_event_consumer` reads queue in async context, writes to DB

## Key Patterns

- Services raise domain exceptions (ValueError, etc.) — routers handle HTTPException conversion
- Use `project_filter()` / `project_count_filter()` from `src.utils.query` for all project-scoped queries
- Return SQLModel instances (not schemas) — routers convert via response schemas
- `IntegrityError` handling at router level using `is_unique_violation()` / `is_foreign_key_violation()`
- Task services are stateless singletons (no `__init__` with project_id) — project_id passed per-call
- Daily report / resource usage services are stateful (project_id in constructor) — instantiated via factory functions
