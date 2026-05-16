"""add_location_to_messages

Revision ID: ffc37f75f094
Revises: 4823fb67606d
Create Date: 2026-05-16 22:29:35.773278

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ffc37f75f094"
down_revision: str | Sequence[str] | None = "4823fb67606d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("messages", sa.Column("location_lat", sa.Float(), nullable=True))
    op.add_column("messages", sa.Column("location_lng", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_messages_location_pair_set",
        "messages",
        "(location_lat IS NULL) = (location_lng IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_messages_location_pair_set", "messages", type_="check")
    op.drop_column("messages", "location_lng")
    op.drop_column("messages", "location_lat")
