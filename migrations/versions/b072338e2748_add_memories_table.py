"""add memories table

Revision ID: b072338e2748
Revises: b614104a2ebe
Create Date: 2026-05-09 09:33:39.286886

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b072338e2748"
down_revision: str | Sequence[str] | None = "b614104a2ebe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Time(), nullable=True),
        sa.Column(
            "event_tz",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'UTC'"),
        ),
        sa.Column("location_lat", sa.Float(), nullable=True),
        sa.Column("location_lng", sa.Float(), nullable=True),
        sa.Column("location_label", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.LargeBinary(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column(
            "external_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unsynced'"),
        ),
        sa.Column(
            "external_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("external_error", sa.Text(), nullable=True),
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(text, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(content_hash) = 32",
            name="ck_memories_content_hash_len",
        ),
        sa.CheckConstraint(
            "(location_lat IS NULL) = (location_lng IS NULL)",
            name="ck_memories_location_paired",
        ),
        sa.CheckConstraint(
            "location_lat IS NULL OR location_lat BETWEEN -90 AND 90",
            name="ck_memories_location_lat_range",
        ),
        sa.CheckConstraint(
            "location_lng IS NULL OR location_lng BETWEEN -180 AND 180",
            name="ck_memories_location_lng_range",
        ),
        sa.CheckConstraint(
            "external_status IN ('synced','unsynced','pending_delete')",
            name="ck_memories_external_status",
        ),
    )

    op.create_index(
        "ux_memories_user_content_hash",
        "memories",
        ["user_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_index(
        "ix_memories_user_event_date_id",
        "memories",
        [sa.text("user_id"), sa.text("event_date DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_index(
        "ix_memories_search_tsv_gin",
        "memories",
        ["search_tsv"],
        postgresql_using="gin",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_index(
        "ix_memories_external_status_pending",
        "memories",
        ["external_status"],
        postgresql_where=sa.text("external_status <> 'synced'"),
    )


def downgrade() -> None:
    op.drop_table("memories")
