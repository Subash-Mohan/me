from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


Role = Literal["user", "assistant"]


class Message(Base):
    """One turn-side of a chat session.

    The user-message row's `id` is the client-supplied UUID so dup retries hit
    the PK directly. The assistant row links back via `parent_message_id`, and
    the partial UNIQUE on that column guarantees one assistant reply per user
    turn (until either is soft-deleted).
    """

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[Role] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    parent_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    client_tz: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('user','assistant')",
            name="ck_messages_role",
        ),
        CheckConstraint(
            "(role = 'assistant') OR (events IS NULL)",
            name="ck_messages_events_assistant_only",
        ),
        CheckConstraint(
            "(role = 'user') OR (parent_message_id IS NOT NULL)",
            name="ck_messages_assistant_has_parent",
        ),
        CheckConstraint(
            "(location_lat IS NULL) = (location_lng IS NULL)",
            name="ck_messages_location_pair_set",
        ),
        Index(
            "ix_messages_session_created_at",
            "session_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_messages_user",
            "user_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ux_messages_parent",
            "parent_message_id",
            unique=True,
            postgresql_where=text("parent_message_id IS NOT NULL AND deleted_at IS NULL"),
        ),
    )
