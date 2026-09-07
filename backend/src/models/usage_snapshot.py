"""usage_snapshot 物化视图：非 ORM 数据源。

usage_snapshot 不是 SQLModel 表模型，而是由 alembic 迁移创建的
PostgreSQL 物化视图（见 backend/alembic/versions/c4d5e6f7a8b9_*.py 中的
_USAGE_SNAPSHOT_SQL），按 (project, usage) 行把资源/任务/用量三类实体
标签与资源分类（分类显示名，与项目默认标签同名）按**名称**合并为 tags[]，供饼图聚合与
用量「合并标签」检索读取。

刷新（30min 后台 / 惰性 / 手动）见 src/services/usage_snapshot.py；
行级只读查询辅助见 src/services/usage_snapshot_query.py。
"""
