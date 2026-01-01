"""Add supporters table

Revision ID: 265ebbd65cab
Revises: 717558224610
Create Date: 2026-01-01 13:51:55.964418

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "265ebbd65cab"
down_revision: Union[str, Sequence[str], None] = "717558224610"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "members",
        sa.Column("id", sa.BIGINT, primary_key=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("members")
