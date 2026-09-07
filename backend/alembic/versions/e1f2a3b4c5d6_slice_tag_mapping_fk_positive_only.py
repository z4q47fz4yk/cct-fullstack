"""slice_tag_mapping.tag_id 改真实 FK（废除负数内置标签 id）

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-08 12:00:00.000000

设计：
- 废除「负数内置分类标签」概念：分类过滤不再用负 id 伪标签，改由项目级
  默认标签（is_default=true，名称=资源分类显示名，见 d0e1f2a3b4c5 回填）
  承载。slice_tag_mapping.tag_id 从此一律引用真实 tag 行。
- 升级顺序：
  1. 存量负数行 → 目标项目内同名默认标签（旧 -1..-5 ↔ 人工/机械/材料/
     运输/其他）；目标不存在则删除该行（d0e1f2a3b4c5 已保证每项目回填，
     此分支为防御）；
  2. 删除旧 CHECK ``ck_slice_tag_mapping_tag_id_nonzero``（tag_id <> 0）；
  3. 新增 CHECK ``tag_id > 0``（防负数残留）；
  4. tag_id 建 FK → tag.id ON DELETE CASCADE（标签删除自动清理切片引用，
     替代原服务层手工删除）；tag_id 加索引便于按标签反查。
- 降级：删除 FK/新 CHECK/索引，恢复 ``tag_id <> 0``；把引用「默认分类
  标签行」的映射按名称还原为旧负数 id（尽力对称，开发期数据可弃）。
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 旧负数 id → 分类显示名（与 d0e1f2a3b4c5 写入的默认标签名一致）
_LEGACY_NEG_ID_TO_NAME: dict[int, str] = {
    -1: "人工",
    -2: "机械",
    -3: "材料",
    -4: "运输",
    -5: "其他",
}
# 分类显示名 → 旧负数 id（降级还原用）
_NAME_TO_LEGACY_NEG_ID: dict[str, int] = {
    v: k for k, v in _LEGACY_NEG_ID_TO_NAME.items()
}


def _drop_tag_id_check() -> None:
    op.drop_constraint(
        "ck_slice_tag_mapping_tag_id_nonzero", "slice_tag_mapping", type_="check"
    )


def _add_positive_check() -> None:
    op.create_check_constraint(
        "ck_slice_tag_mapping_tag_id_positive",
        "slice_tag_mapping",
        "tag_id > 0",
    )


def upgrade() -> None:
    """Upgrade schema：负数行转默认标签行 → tag_id 建 FK 与正数 CHECK。"""
    conn = op.get_bind()

    # 1. 转换存量负数行：映射到同项目内同名默认标签
    rows = conn.execute(
        sa.text(
            "SELECT m.slice_id, m.tag_id, s.project_id "
            "FROM slice_tag_mapping m JOIN slice s ON s.id = m.slice_id "
            "WHERE m.tag_id < 0"
        )
    ).fetchall()

    for slice_id, tag_id, project_id in rows:
        name = _LEGACY_NEG_ID_TO_NAME.get(tag_id)
        if name is None:
            # 未知负数：直接删除（防御）
            conn.execute(
                sa.text(
                    "DELETE FROM slice_tag_mapping "
                    "WHERE slice_id = :sid AND tag_id = :tid"
                ),
                {"sid": slice_id, "tid": tag_id},
            )
            continue
        target = conn.execute(
            sa.text(
                "SELECT id FROM tag "
                "WHERE project_id = :pid AND name = :name AND is_default = true"
            ),
            {"pid": project_id, "name": name},
        ).fetchone()
        if target is None:
            # 默认标签缺失（理论不发生）：删除该映射，避免悬挂
            conn.execute(
                sa.text(
                    "DELETE FROM slice_tag_mapping "
                    "WHERE slice_id = :sid AND tag_id = :tid"
                ),
                {"sid": slice_id, "tid": tag_id},
            )
            continue
        conn.execute(
            sa.text(
                "UPDATE slice_tag_mapping SET tag_id = :new_tid "
                "WHERE slice_id = :sid AND tag_id = :tid"
            ),
            {"sid": slice_id, "tid": tag_id, "new_tid": target[0]},
        )

    # 2. 替换 CHECK 约束
    _drop_tag_id_check()
    _add_positive_check()

    # 3. tag_id 建 FK（ON DELETE CASCADE：删标签自动清切片引用）
    op.create_foreign_key(
        "fk_slice_tag_mapping_tag_id",
        "slice_tag_mapping",
        "tag",
        ["tag_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_slice_tag_mapping_tag_id"),
        "slice_tag_mapping",
        ["tag_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema（尽力对称，开发期数据可弃）。"""
    conn = op.get_bind()

    # 1. 删 FK / 索引 / 新 CHECK
    op.drop_index(op.f("ix_slice_tag_mapping_tag_id"), table_name="slice_tag_mapping")
    op.drop_constraint(
        "fk_slice_tag_mapping_tag_id", "slice_tag_mapping", type_="foreignkey"
    )
    op.drop_constraint(
        "ck_slice_tag_mapping_tag_id_positive", "slice_tag_mapping", type_="check"
    )
    op.create_check_constraint(
        "ck_slice_tag_mapping_tag_id_nonzero",
        "slice_tag_mapping",
        "tag_id <> 0",
    )

    # 2. 引用默认分类标签行的映射还原为旧负数 id（按名称判定）
    rows = conn.execute(
        sa.text(
            "SELECT m.slice_id, m.tag_id, tag.name, s.project_id "
            "FROM slice_tag_mapping m "
            "JOIN slice s ON s.id = m.slice_id "
            "JOIN tag ON tag.id = m.tag_id "
            "WHERE tag.is_default = true"
        )
    ).fetchall()
    for slice_id, tag_id, name, _project_id in rows:
        neg = _NAME_TO_LEGACY_NEG_ID.get(name)
        if neg is None:
            continue  # 非资源类别默认标签（如未来新增默认分组），保持正 id
        conn.execute(
            sa.text(
                "UPDATE slice_tag_mapping SET tag_id = :neg "
                "WHERE slice_id = :sid AND tag_id = :tid"
            ),
            {"sid": slice_id, "tid": tag_id, "neg": neg},
        )
