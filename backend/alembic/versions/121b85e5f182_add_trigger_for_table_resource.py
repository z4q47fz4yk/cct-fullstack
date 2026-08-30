"""add trigger for table resource

Revision ID: 121b85e5f182
Revises: 6300ba5e730e
Create Date: 2026-02-27 12:46:29.404833

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "121b85e5f182"
down_revision: Union[str, Sequence[str], None] = "6300ba5e730e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            # sql
            """
        CREATE TRIGGER update_resource_updated_at
            BEFORE UPDATE
            ON resource
            FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
        """
        )
    )
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            # sql
            """
        DROP TRIGGER update_resource_updated_at ON resource;
        """
        )
    )
    pass
