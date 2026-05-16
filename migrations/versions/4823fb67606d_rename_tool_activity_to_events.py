"""rename tool_activity to events

Revision ID: 4823fb67606d
Revises: 588dbc1f14e4
Create Date: 2026-05-16 18:46:08.021229

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4823fb67606d"
down_revision: str | Sequence[str] | None = "588dbc1f14e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        "ck_messages_tool_activity_assistant_only",
        "messages",
        type_="check",
    )
    op.alter_column("messages", "tool_activity", new_column_name="events")
    op.create_check_constraint(
        "ck_messages_events_assistant_only",
        "messages",
        "(role = 'assistant') OR (events IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_messages_events_assistant_only",
        "messages",
        type_="check",
    )
    op.alter_column("messages", "events", new_column_name="tool_activity")
    op.create_check_constraint(
        "ck_messages_tool_activity_assistant_only",
        "messages",
        "(role = 'assistant') OR (tool_activity IS NULL)",
    )
