from datetime import UTC, date, datetime, time
from typing import Literal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    LargeBinary,
    Text,
    Time,
    column,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


ExternalStatus = Literal["synced", "unsynced", "pending_delete"]


class Memory(Base):
    """A user-curated memory.

    `id` doubles as Supermemory's `customId` and as the dedupe key for
    `create_memory` — passing the same id returns the existing row.

    `search_tsv` is a generated tsvector. It is mapped so ORM metadata
    matches the DB; reads go through raw SQL, not the ORM.
    """

    __tablename__ = "memories"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sql_text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    event_tz: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=sql_text("'UTC'"),
    )
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_status: Mapped[ExternalStatus] = mapped_column(
        Text,
        nullable=False,
        server_default=sql_text("'unsynced'"),
    )
    external_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    external_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(text, ''))",
            persisted=True,
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
        onupdate=_utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "octet_length(content_hash) = 32",
            name="ck_memories_content_hash_len",
        ),
        CheckConstraint(
            "(location_lat IS NULL) = (location_lng IS NULL)",
            name="ck_memories_location_paired",
        ),
        CheckConstraint(
            "location_lat IS NULL OR location_lat BETWEEN -90 AND 90",
            name="ck_memories_location_lat_range",
        ),
        CheckConstraint(
            "location_lng IS NULL OR location_lng BETWEEN -180 AND 180",
            name="ck_memories_location_lng_range",
        ),
        CheckConstraint(
            "external_status IN ('synced','unsynced','pending_delete')",
            name="ck_memories_external_status",
        ),
        Index(
            "ux_memories_user_content_hash",
            "user_id",
            "content_hash",
            unique=True,
            postgresql_where=sql_text("deleted_at IS NULL"),
        ),
        Index(
            "ix_memories_user_event_date_id",
            column("user_id"),
            column("event_date").desc(),
            column("id").desc(),
            postgresql_where=sql_text("deleted_at IS NULL"),
        ),
        Index(
            "ix_memories_search_tsv_gin",
            column("search_tsv"),
            postgresql_using="gin",
            postgresql_where=sql_text("deleted_at IS NULL"),
        ),
        Index(
            "ix_memories_external_status_pending",
            "external_status",
            postgresql_where=sql_text("external_status <> 'synced'"),
        ),
    )
