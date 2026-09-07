"""merge weather daily granularity and tag slice refactor

Revision ID: b7df4cbe0e5e
Revises: a83d722a525b, e1f2a3b4c5d6
Create Date: 2026-09-07 20:57:33.322608

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b7df4cbe0e5e"
down_revision: Union[str, Sequence[str], None] = ("a83d722a525b", "e1f2a3b4c5d6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
