"""add a function for `updated_at` autoupdate

Revision ID: 6300ba5e730e
Revises: 2c3b6921e76c
Create Date: 2026-02-27 12:43:54.202578

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6300ba5e730e"
down_revision: Union[str, Sequence[str], None] = "2c3b6921e76c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            # sql
            """
        CREATE FUNCTION update_updated_at_column()
            RETURNS trigger AS
        $$
        BEGIN
            new.updated_at = statement_timestamp();
            RETURN new;
        END;
        $$ LANGUAGE plpgsql;
        """
        )
    )
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        # sql
        """
        DROP FUNCTION update_updated_at_column;
        """
    )
    pass
