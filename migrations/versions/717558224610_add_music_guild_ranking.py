"""Add music guild ranking

Revision ID: 717558224610
Revises:
Create Date: 2026-01-01 13:47:49.469465

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "717558224610"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "guilds",
        sa.Column("id", sa.BIGINT, primary_key=True),
        sa.Column("played_musics", sa.JSON(True), server_default="[]"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("guilds")
