"""add tag.is_default and backfill default tags for existing projects

Revision ID: d0e1f2a3b4c5
Revises: cd1fdff23a92
Create Date: 2026-09-08 10:00:00.000000

设计：
- 标签表新增 ``is_default``（NOT NULL，默认 false），标识项目级默认标签。
- 升级时遍历现有项目，按 ``DEFAULT_PROJECT_TAGS`` 规格补齐默认标签：
  - 同名标签已存在则仅置 ``is_default = true``，不改 name/group/description
    （避免覆盖用户数据，也避免与项目内已有同名标签产生冲突）；
  - 否则按规格新插入。
- 由于 ``DEFAULT_PROJECT_TAGS`` 名称与资源分类显示名（人工/机械/材料/运输/其他）一致，
  写入后与 ``usage_snapshot`` 物化视图按名称合并标签的口径保持一致。
- 降级：删除 ``is_default`` 列（默认标签随项目级 CASCADE 删除时一并消失）。
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "cd1fdff23a92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 默认标签规格（与 src.schemas.tag.DEFAULT_PROJECT_TAGS 一致，确保迁移脚本
# 无需依赖业务代码即可独立执行）。
DEFAULT_TAG_GROUP = "资源类别"
DEFAULT_TAGS: list[str] = [
    "人工",
    "机械",
    "材料",
    "运输",
    "其他",
]


def upgrade() -> None:
    """升级：新增 is_default 列并回填默认标签。"""
    # 1. 新增 is_default 列（NOT NULL），先用临时默认值回填已有行
    op.add_column(
        "tag",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # 不需要额外的 server_default 持久化：False 已是模型默认值，写入语义不变

    # 2. 遍历现有项目，补齐默认标签
    conn = op.get_bind()

    # 现有项目 id 列表
    project_rows = conn.execute(sa.text("SELECT id FROM project")).fetchall()
    project_ids: list[int] = [row[0] for row in project_rows]

    for pid in project_ids:
        for name in DEFAULT_TAGS:
            existing = conn.execute(
                sa.text(
                    "SELECT id, is_default FROM tag "
                    "WHERE project_id = :pid AND name = :name"
                ),
                {"pid": pid, "name": name},
            ).fetchone()
            if existing is not None:
                # 同名标签已存在：仅标记为默认，不覆盖用户自定义字段
                conn.execute(
                    sa.text(
                        "UPDATE tag SET is_default = true "
                        "WHERE id = :tid AND is_default = false"
                    ),
                    {"tid": existing[0]},
                )
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO tag "
                    '(project_id, name, "group", description, is_default, '
                    " created_at, updated_at) "
                    "VALUES "
                    "(:pid, :name, :group, :description, true, "
                    " now(), now())"
                ),
                {
                    "pid": pid,
                    "name": name,
                    "group": DEFAULT_TAG_GROUP,
                    "description": "系统默认资源类别标签",
                },
            )


def downgrade() -> None:
    """降级：删除 is_default 列。

    默认标签随项目级 CASCADE 仍保留在表中（仅去掉标记），不强制清理，避免误删
    用户可能复用默认名称建立的业务标签。调用方若需清理由独立 SQL 完成。
    """
    op.drop_column("tag", "is_default")
