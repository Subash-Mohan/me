"""Integration tests for the memory service layer.

Real Postgres + `FakeMemoryClient`. The `owner_id` fixture is function-scoped
and calls `reset_db()`, so every test starts from a clean DB with a freshly
seeded owner — tests do not share state.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.services import memory as memory_service
from app.services.memory import (
    MemoryIdempotencyReused,
    MemoryNotFound,
    MemoryValidationError,
)
from tests._db import reset_db, seed_memory, seed_owner
from tests._memory_client_fake import FakeMemoryClient


@pytest.fixture
def owner_id() -> UUID:
    reset_db()
    return seed_owner("phrase for memory tests")


# ─── get_memory ────────────────────────────────────────────────────────────


class TestGetMemory:
    def test_returns_row_for_owner(self, db: Session, owner_id: UUID) -> None:
        mid = seed_memory(user_id=owner_id, text_body="hello get")
        row = memory_service.get_memory(db, user_id=owner_id, memory_id=mid)
        assert row.id == mid
        assert row.text == "hello get"

    def test_raises_not_found_when_missing(self, db: Session, owner_id: UUID) -> None:
        with pytest.raises(MemoryNotFound):
            memory_service.get_memory(db, user_id=owner_id, memory_id=uuid4())

    def test_hides_soft_deleted(self, db: Session, owner_id: UUID) -> None:
        mid = seed_memory(
            user_id=owner_id,
            text_body="soft deleted",
            deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
        )
        with pytest.raises(MemoryNotFound):
            memory_service.get_memory(db, user_id=owner_id, memory_id=mid)

    def test_cross_user_returns_not_found(self, db: Session, owner_id: UUID) -> None:
        mid = seed_memory(user_id=owner_id, text_body="my secret")
        other = uuid4()
        with pytest.raises(MemoryNotFound):
            memory_service.get_memory(db, user_id=other, memory_id=mid)


# ─── list_memories ─────────────────────────────────────────────────────────


class TestListMemories:
    def test_returns_empty_list_when_no_rows(self, db: Session, owner_id: UUID) -> None:
        rows, cursor = memory_service.list_memories(db, user_id=owner_id)
        assert rows == []
        assert cursor is None

    def test_returns_rows_descending_by_event_date(self, db: Session, owner_id: UUID) -> None:
        # Three rows on three different dates.
        seed_memory(user_id=owner_id, text_body="oldest", event_date=date(2026, 1, 1))
        seed_memory(user_id=owner_id, text_body="middle", event_date=date(2026, 3, 1))
        seed_memory(user_id=owner_id, text_body="newest", event_date=date(2026, 5, 1))

        rows, cursor = memory_service.list_memories(db, user_id=owner_id)
        assert [r.text for r in rows] == ["newest", "middle", "oldest"]
        assert cursor is None

    def test_paginates_across_two_pages(self, db: Session, owner_id: UUID) -> None:
        seed_memory(user_id=owner_id, text_body="a", event_date=date(2026, 1, 1))
        seed_memory(user_id=owner_id, text_body="b", event_date=date(2026, 2, 1))
        seed_memory(user_id=owner_id, text_body="c", event_date=date(2026, 3, 1))
        seed_memory(user_id=owner_id, text_body="d", event_date=date(2026, 4, 1))

        page1, cursor = memory_service.list_memories(db, user_id=owner_id, limit=2)
        assert [r.text for r in page1] == ["d", "c"]
        assert cursor is not None

        page2, cursor2 = memory_service.list_memories(db, user_id=owner_id, limit=2, cursor=cursor)
        assert [r.text for r in page2] == ["b", "a"]
        assert cursor2 is None

    def test_filters_by_date_range(self, db: Session, owner_id: UUID) -> None:
        seed_memory(user_id=owner_id, text_body="jan", event_date=date(2026, 1, 15))
        seed_memory(user_id=owner_id, text_body="mar", event_date=date(2026, 3, 15))
        seed_memory(user_id=owner_id, text_body="may", event_date=date(2026, 5, 15))

        rows, _ = memory_service.list_memories(
            db,
            user_id=owner_id,
            from_date=date(2026, 2, 1),
            to_date=date(2026, 4, 1),
        )
        assert [r.text for r in rows] == ["mar"]

    def test_excludes_soft_deleted(self, db: Session, owner_id: UUID) -> None:
        seed_memory(user_id=owner_id, text_body="alive", event_date=date(2026, 5, 1))
        seed_memory(
            user_id=owner_id,
            text_body="dead",
            event_date=date(2026, 5, 2),
            deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
        )

        rows, _ = memory_service.list_memories(db, user_id=owner_id)
        assert [r.text for r in rows] == ["alive"]

    def test_excludes_other_users(self, db: Session, owner_id: UUID) -> None:
        seed_memory(user_id=owner_id, text_body="mine", event_date=date(2026, 5, 1))
        # Seed a memory for an owner that doesn't exist would violate FK; skip the
        # cross-user case here — covered by the get_memory tests where FK is irrelevant.
        rows, _ = memory_service.list_memories(db, user_id=uuid4())
        assert rows == []

    def test_clamps_limit_to_max(self, db: Session, owner_id: UUID) -> None:
        # Pass a limit way over MAX_PAGE_LIMIT; must not raise, must not return
        # more than MAX_PAGE_LIMIT (we have only one row, so this asserts no crash).
        seed_memory(user_id=owner_id, text_body="solo", event_date=date(2026, 5, 1))
        rows, _ = memory_service.list_memories(
            db, user_id=owner_id, limit=memory_service.MAX_PAGE_LIMIT + 5_000
        )
        assert len(rows) == 1

    def test_clamps_negative_limit_to_one(self, db: Session, owner_id: UUID) -> None:
        seed_memory(user_id=owner_id, text_body="x", event_date=date(2026, 5, 1))
        rows, _ = memory_service.list_memories(db, user_id=owner_id, limit=-5)
        assert len(rows) == 1

    def test_malformed_cursor_raises_validation_error(self, db: Session, owner_id: UUID) -> None:
        with pytest.raises(MemoryValidationError):
            memory_service.list_memories(db, user_id=owner_id, cursor="not-a-cursor")


# ─── Memory ORM is the return type (not Pydantic) ──────────────────────────


def test_get_memory_returns_orm_row(db: Session, owner_id: UUID) -> None:
    mid = seed_memory(user_id=owner_id, text_body="orm row check")
    row = memory_service.get_memory(db, user_id=owner_id, memory_id=mid)
    assert isinstance(row, Memory)


def test_unused_fixture_marker(memory_client: FakeMemoryClient) -> None:
    """Sanity: the fake fixture is wired and instantiable. Used by later tests."""
    assert memory_client is not None


# ─── create_memory ─────────────────────────────────────────────────────────


class TestCreateMemory:
    def test_happy_path_marks_synced_and_calls_client(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="my first entry",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        assert row.text == "my first entry"
        assert row.external_status == "synced"
        assert row.external_id == "doc_" + row.id.hex
        assert row.external_synced_at is not None

        # Client called exactly once with the expected shape.
        ops = [op for op, _ in memory_client.calls]
        assert ops == ["add"]
        _, kwargs = memory_client.calls[0]
        assert kwargs["custom_id"] == row.id
        assert kwargs["container_tags"] == [f"user_{owner_id.hex}"]

    def test_layer1_dedupe_returns_existing_on_repeat_idempotency_id(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        idem = uuid4()
        first = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="first body",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
            idempotency_id=idem,
        )
        # Second call with the same idempotency_id but a *different* body
        # must still return the existing row — that's the point of idem keys.
        second = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="totally different body",
            event_date=date(2026, 5, 9),
            event_tz="UTC",
            idempotency_id=idem,
        )
        assert second.id == first.id
        assert second.text == "first body"  # unchanged
        assert [op for op, _ in memory_client.calls] == ["add"]  # only the first call

    def test_layer2_dedupe_returns_existing_on_same_text(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        first = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="duplicate body",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        # Same text → same content_hash → ON CONFLICT DO NOTHING → fetch existing.
        second = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="DUPLICATE BODY",  # casing irrelevant — canonical hash strips it
            event_date=date(2026, 5, 9),
            event_tz="UTC",
        )
        assert second.id == first.id
        # Only the first call hits the client; second short-circuits via dedupe.
        assert len(memory_client.calls) == 1

    def test_empty_text_raises_validation(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        with pytest.raises(MemoryValidationError):
            memory_service.create_memory(
                db,
                memory_client,
                user_id=owner_id,
                text="   ",
                event_date=date(2026, 5, 8),
                event_tz="UTC",
            )

    def test_invalid_tz_raises_validation(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        with pytest.raises(MemoryValidationError):
            memory_service.create_memory(
                db,
                memory_client,
                user_id=owner_id,
                text="hello",
                event_date=date(2026, 5, 8),
                event_tz="Not/A/Zone",
            )

    def test_lat_without_lng_raises_validation(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        with pytest.raises(MemoryValidationError):
            memory_service.create_memory(
                db,
                memory_client,
                user_id=owner_id,
                text="lonely lat",
                event_date=date(2026, 5, 8),
                event_tz="UTC",
                location_lat=37.0,
            )

    def test_out_of_range_lat_raises_validation(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        with pytest.raises(MemoryValidationError):
            memory_service.create_memory(
                db,
                memory_client,
                user_id=owner_id,
                text="off the map",
                event_date=date(2026, 5, 8),
                event_tz="UTC",
                location_lat=120.0,
                location_lng=10.0,
            )

    def test_client_transient_failure_marks_unsynced_without_raising(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        from app.services.memory_client import MemoryClientTransientError

        memory_client.fail_next("add", error=MemoryClientTransientError("boom"))
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="will not sync",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        assert row.external_status == "unsynced"
        assert row.external_error == "MemoryClientTransientError"
        assert row.external_id is None

    def test_client_permanent_failure_logs_warning_and_marks_unsynced(
        self,
        db: Session,
        owner_id: UUID,
        memory_client: FakeMemoryClient,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from app.services.memory_client import MemoryClientPermanentError

        memory_client.fail_next("add", error=MemoryClientPermanentError("bad payload"))
        capsys.readouterr()  # drain prior output
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="malformed",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        captured = capsys.readouterr()
        assert row.external_status == "unsynced"
        assert row.external_error == "MemoryClientPermanentError"
        # structlog writes JSON to stdout. The op-log event must be present.
        assert "memory.external_permanent_err" in captured.out

    def test_can_recreate_after_soft_delete(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        seed_memory(
            user_id=owner_id,
            text_body="phoenix",
            deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
        )
        # Same text after a soft-delete must be insertable again — partial
        # unique index excludes deleted_at IS NULL, so no conflict.
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="phoenix",
            event_date=date(2026, 5, 9),
            event_tz="UTC",
        )
        assert row.deleted_at is None
        assert row.text == "phoenix"

    def test_reusing_idempotency_id_of_soft_deleted_raises(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        # Seed a soft-deleted row, then retry create_memory with the same
        # idempotency_id (= primary key). Layer-1 lookup must see the tombstone
        # and raise rather than letting the INSERT crash on the unconditional
        # PK constraint.
        idem = uuid4()
        seed_memory(
            user_id=owner_id,
            text_body="ghost",
            deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
            id=idem,
        )
        with pytest.raises(MemoryIdempotencyReused):
            memory_service.create_memory(
                db,
                memory_client,
                user_id=owner_id,
                text="reborn body",
                event_date=date(2026, 5, 9),
                event_tz="UTC",
                idempotency_id=idem,
            )
        # No client call — the failure happens before the SDK is touched.
        assert memory_client.calls == []


# ─── update_memory ─────────────────────────────────────────────────────────


class TestUpdateMemory:
    def test_updates_text_and_recomputes_hash(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="original",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        memory_client.calls.clear()

        updated = memory_service.update_memory(
            db, memory_client, user_id=owner_id, memory_id=row.id, text="rewritten"
        )
        assert updated.text == "rewritten"
        assert updated.external_status == "synced"
        # Patch is the right SDK op for an already-synced doc.
        ops = [op for op, _ in memory_client.calls]
        assert ops == ["patch"]

    def test_updates_location_label_to_none(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="had a label",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
            location_label="HQ",
        )
        updated = memory_service.update_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=row.id,
            location_label=None,
        )
        assert updated.location_label is None

    def test_unset_fields_are_left_alone(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="hi",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
            location_label="kept",
        )
        # Update only text. The label must NOT be cleared.
        updated = memory_service.update_memory(
            db, memory_client, user_id=owner_id, memory_id=row.id, text="hello"
        )
        assert updated.location_label == "kept"

    def test_invalid_tz_raises_validation(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="t",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        with pytest.raises(MemoryValidationError):
            memory_service.update_memory(
                db,
                memory_client,
                user_id=owner_id,
                memory_id=row.id,
                event_tz="Not/A/Zone",
            )

    def test_resulting_lat_lng_pair_must_be_valid(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="paired",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
            location_lat=10.0,
            location_lng=20.0,
        )
        # Patching only lat to None leaves lng=20 with lat=NULL → invalid pair.
        with pytest.raises(MemoryValidationError):
            memory_service.update_memory(
                db,
                memory_client,
                user_id=owner_id,
                memory_id=row.id,
                location_lat=None,
            )

    def test_text_collision_raises_duplicate(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        from app.services.memory import MemoryDuplicate

        memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="taken",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        other = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="open",
            event_date=date(2026, 5, 9),
            event_tz="UTC",
        )
        with pytest.raises(MemoryDuplicate):
            memory_service.update_memory(
                db,
                memory_client,
                user_id=owner_id,
                memory_id=other.id,
                text="taken",
            )

    def test_update_missing_row_raises_not_found(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        with pytest.raises(MemoryNotFound):
            memory_service.update_memory(
                db,
                memory_client,
                user_id=owner_id,
                memory_id=uuid4(),
                text="ghost",
            )

    def test_update_soft_deleted_row_raises_not_found(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        mid = seed_memory(
            user_id=owner_id,
            text_body="dead",
            deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
        )
        with pytest.raises(MemoryNotFound):
            memory_service.update_memory(
                db,
                memory_client,
                user_id=owner_id,
                memory_id=mid,
                text="resurrect",
            )

    def test_update_cross_user_raises_not_found(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="mine",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        with pytest.raises(MemoryNotFound):
            memory_service.update_memory(
                db,
                memory_client,
                user_id=uuid4(),
                memory_id=row.id,
                text="hijack",
            )

    def test_client_patch_failure_marks_unsynced(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        from app.services.memory_client import MemoryClientTransientError

        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="will lose sync",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        memory_client.fail_next("patch", error=MemoryClientTransientError("boom"))
        updated = memory_service.update_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=row.id,
            text="updated body",
        )
        assert updated.external_status == "unsynced"
        assert updated.external_error == "MemoryClientTransientError"

    def test_update_calls_add_when_external_id_is_null(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        # Seed a row that never made it to Supermemory (external_id NULL,
        # external_status='unsynced'). The update must call `add`, not `patch`.
        mid = seed_memory(
            user_id=owner_id,
            text_body="orphan",
            external_status="unsynced",
        )
        memory_service.update_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=mid,
            text="adopted",
        )
        ops = [op for op, _ in memory_client.calls]
        assert ops == ["add"]

    def test_update_advances_external_synced_at_on_patch(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        # The patch success path must refresh `external_synced_at`.
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="initial",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        first_sync = row.external_synced_at
        assert first_sync is not None

        updated = memory_service.update_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=row.id,
            text="revised",
        )
        assert updated.external_status == "synced"
        assert updated.external_synced_at is not None
        assert updated.external_synced_at >= first_sync


# ─── delete_memory ─────────────────────────────────────────────────────────


class TestDeleteMemory:
    def test_soft_deletes_and_calls_client(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="goodbye",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        memory_client.calls.clear()

        result = memory_service.delete_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=row.id,
        )
        assert result is None

        # Hidden from get/list.
        with pytest.raises(MemoryNotFound):
            memory_service.get_memory(db, user_id=owner_id, memory_id=row.id)

        ops = [op for op, _ in memory_client.calls]
        assert ops == ["delete"]

    def test_idempotent_when_already_deleted(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        mid = seed_memory(
            user_id=owner_id,
            text_body="zombie",
            deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
        )
        # Second delete is a no-op — must not raise, must not re-call the client.
        memory_service.delete_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=mid,
        )
        assert memory_client.calls == []

    def test_missing_row_raises_not_found(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        with pytest.raises(MemoryNotFound):
            memory_service.delete_memory(
                db,
                memory_client,
                user_id=owner_id,
                memory_id=uuid4(),
            )

    def test_cross_user_raises_not_found(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="off-limits",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        with pytest.raises(MemoryNotFound):
            memory_service.delete_memory(
                db,
                memory_client,
                user_id=uuid4(),
                memory_id=row.id,
            )

    def test_client_failure_marks_pending_delete(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        from app.services.memory_client import MemoryClientTransientError

        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="leaks",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        memory_client.fail_next("delete", error=MemoryClientTransientError("boom"))
        memory_service.delete_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=row.id,
        )

        # Re-load via raw select so the soft-deleted row is visible.
        from sqlalchemy import select as _select

        from app.models.memory import Memory as _Memory

        refreshed = db.execute(_select(_Memory).where(_Memory.id == row.id)).scalar_one()
        assert refreshed.deleted_at is not None
        assert refreshed.external_status == "pending_delete"
        assert refreshed.external_error == "MemoryClientTransientError"

    def test_no_client_call_when_external_id_is_null(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        mid = seed_memory(
            user_id=owner_id,
            text_body="never-synced",
            external_status="unsynced",
        )
        # No external_id → nothing to delete remotely.
        memory_service.delete_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=mid,
        )
        assert memory_client.calls == []

    def test_happy_path_resets_external_status_to_synced(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        # After successful delete, status must read 'synced' so a later
        # sync_memory cannot route through the patch branch.
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="will be deleted",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        memory_service.delete_memory(db, memory_client, user_id=owner_id, memory_id=row.id)

        from sqlalchemy import select as _select

        from app.models.memory import Memory as _Memory

        refreshed = db.execute(_select(_Memory).where(_Memory.id == row.id)).scalar_one()
        assert refreshed.deleted_at is not None
        assert refreshed.external_status == "synced"
        assert refreshed.external_error is None

    def test_unsynced_with_external_id_delete_clears_status(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        # Reproduces the regression the status reset guards against:
        # row was already in 'unsynced' with an external_id; a successful
        # delete must clear the unsynced flag, not leave it pointing at a
        # now-deleted Supermemory document.
        mid = seed_memory(
            user_id=owner_id,
            text_body="orphan-with-doc",
            external_status="unsynced",
            external_id="doc_orphan",
            external_error="MemoryClientTransientError",
        )
        memory_service.delete_memory(db, memory_client, user_id=owner_id, memory_id=mid)

        from sqlalchemy import select as _select

        from app.models.memory import Memory as _Memory

        refreshed = db.execute(_select(_Memory).where(_Memory.id == mid)).scalar_one()
        assert refreshed.external_status == "synced"
        assert refreshed.external_error is None
        # And a follow-up sync_memory must short-circuit (no client call).
        memory_client.calls.clear()
        memory_service.sync_memory(db, memory_client, user_id=owner_id, memory_id=mid)
        assert memory_client.calls == []


# ─── search_memories ───────────────────────────────────────────────────────


class TestSearchMemories:
    def test_supermemory_path_hydrates_hits_in_order(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        from app.services.memory_client import SearchHit as ClientSearchHit

        # Seed three rows — synced — and capture their external_ids.
        rows: list[tuple[str, UUID]] = []
        for text in ("alpha", "bravo", "charlie"):
            r = memory_service.create_memory(
                db,
                memory_client,
                user_id=owner_id,
                text=text,
                event_date=date(2026, 5, 8),
                event_tz="UTC",
            )
            assert r.external_id is not None
            rows.append((r.external_id, r.id))

        # Order the fake's search response: charlie, alpha, bravo
        memory_client.set_search_results(
            [
                ClientSearchHit(doc_id=rows[2][0], similarity=0.91),
                ClientSearchHit(doc_id=rows[0][0], similarity=0.55),
                ClientSearchHit(doc_id=rows[1][0], similarity=0.30),
            ]
        )

        result = memory_service.search_memories(
            db,
            memory_client,
            user_id=owner_id,
            q="anything",
            limit=10,
        )
        assert result.source == "supermemory"
        ids = [row.id for row, _ in result.hits]
        sims = [sim for _, sim in result.hits]
        assert ids == [rows[2][1], rows[0][1], rows[1][1]]
        assert sims == [0.91, 0.55, 0.30]

    def test_supermemory_hits_pointing_to_soft_deleted_rows_are_dropped(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        from app.services.memory_client import SearchHit as ClientSearchHit

        # Seed two rows; soft-delete one directly.
        live = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="alive",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        dead = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="dead",
            event_date=date(2026, 5, 9),
            event_tz="UTC",
        )
        # Soft-delete the second one via raw SQL to avoid going through delete_memory
        from datetime import datetime as _dt

        from sqlalchemy import update as _update

        from app.models.memory import Memory as _Memory

        db.execute(
            _update(_Memory)
            .where(_Memory.id == dead.id)
            .values(deleted_at=_dt(2026, 5, 8, tzinfo=UTC))
        )
        db.commit()

        assert live.external_id is not None
        assert dead.external_id is not None
        memory_client.set_search_results(
            [
                ClientSearchHit(doc_id=dead.external_id, similarity=0.95),
                ClientSearchHit(doc_id=live.external_id, similarity=0.50),
            ]
        )

        result = memory_service.search_memories(
            db,
            memory_client,
            user_id=owner_id,
            q="x",
            limit=10,
        )
        assert [r.id for r, _ in result.hits] == [live.id]

    def test_search_falls_back_to_local_on_client_error(
        self,
        db: Session,
        owner_id: UUID,
        memory_client: FakeMemoryClient,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="my smoothie recipe",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="totally unrelated entry",
            event_date=date(2026, 5, 9),
            event_tz="UTC",
        )

        memory_client.fail_next("search")
        capsys.readouterr()
        result = memory_service.search_memories(
            db,
            memory_client,
            user_id=owner_id,
            q="smoothie",
            limit=10,
        )
        captured = capsys.readouterr()

        assert result.source == "local"
        assert len(result.hits) == 1
        assert result.hits[0][0].text == "my smoothie recipe"
        # Local fallback returns similarity=None — never leak ts_rank values.
        assert all(sim is None for _, sim in result.hits)
        # Fallback log emitted; q never appears in logs.
        assert "memory.search_fallback" in captured.out
        assert "smoothie" not in captured.out

    def test_search_excludes_other_users(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        # Local-fallback path — fake search returns nothing by default for the
        # supermemory path, so make sure cross-user tsv hits stay filtered.
        memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="banana",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        memory_client.fail_next("search")
        result = memory_service.search_memories(
            db,
            memory_client,
            user_id=uuid4(),
            q="banana",
            limit=10,
        )
        assert result.hits == []

    def test_search_empty_supermemory_returns_empty_supermemory_source(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        # Default fake state returns []; no errors; no fallback.
        result = memory_service.search_memories(
            db,
            memory_client,
            user_id=owner_id,
            q="ghost",
            limit=5,
        )
        assert result.hits == []
        assert result.source == "supermemory"

    def test_search_clamps_limit(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        memory_service.search_memories(
            db,
            memory_client,
            user_id=owner_id,
            q="x",
            limit=memory_service.MAX_PAGE_LIMIT + 1_000,
        )
        # The fake records the limit it was called with.
        _, kwargs = memory_client.calls[-1]
        assert kwargs["limit"] == memory_service.MAX_PAGE_LIMIT


# ─── sync_memory ───────────────────────────────────────────────────────────


class TestSyncMemory:
    def test_synced_status_is_noop(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        row = memory_service.create_memory(
            db,
            memory_client,
            user_id=owner_id,
            text="already synced",
            event_date=date(2026, 5, 8),
            event_tz="UTC",
        )
        assert row.external_status == "synced"
        memory_client.calls.clear()

        result = memory_service.sync_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=row.id,
        )
        assert result.external_status == "synced"
        assert memory_client.calls == []

    def test_unsynced_with_no_external_id_calls_add(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        mid = seed_memory(
            user_id=owner_id,
            text_body="never sent",
            external_status="unsynced",
        )
        memory_service.sync_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=mid,
        )
        ops = [op for op, _ in memory_client.calls]
        assert ops == ["add"]

    def test_unsynced_with_external_id_calls_patch(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        mid = seed_memory(
            user_id=owner_id,
            text_body="needs repatch",
            external_status="unsynced",
            external_id="doc_pre_existing",
        )
        memory_service.sync_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=mid,
        )
        ops = [op for op, _ in memory_client.calls]
        assert ops == ["patch"]

    def test_pending_delete_calls_delete_and_marks_synced(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        from datetime import datetime as _dt

        mid = seed_memory(
            user_id=owner_id,
            text_body="local delete done",
            external_status="pending_delete",
            external_id="doc_zombie",
            deleted_at=_dt(2026, 5, 8, tzinfo=UTC),
        )
        memory_service.sync_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=mid,
        )
        ops = [op for op, _ in memory_client.calls]
        assert ops == ["delete"]

        # Re-load (bypassing soft-delete filter) and check status.
        from sqlalchemy import select as _select

        from app.models.memory import Memory as _Memory

        row = db.execute(_select(_Memory).where(_Memory.id == mid)).scalar_one()
        assert row.external_status == "synced"
        assert row.deleted_at is not None  # local soft-delete preserved

    def test_unsynced_add_failure_keeps_status(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        from app.services.memory_client import MemoryClientTransientError

        mid = seed_memory(
            user_id=owner_id,
            text_body="boom",
            external_status="unsynced",
        )
        memory_client.fail_next("add", error=MemoryClientTransientError("fail"))
        result = memory_service.sync_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=mid,
        )
        assert result.external_status == "unsynced"
        assert result.external_error == "MemoryClientTransientError"

    def test_pending_delete_failure_keeps_pending_delete(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        from datetime import datetime as _dt

        from app.services.memory_client import MemoryClientTransientError

        mid = seed_memory(
            user_id=owner_id,
            text_body="zombie still here",
            external_status="pending_delete",
            external_id="doc_x",
            deleted_at=_dt(2026, 5, 8, tzinfo=UTC),
        )
        memory_client.fail_next("delete", error=MemoryClientTransientError("fail"))
        memory_service.sync_memory(
            db,
            memory_client,
            user_id=owner_id,
            memory_id=mid,
        )

        from sqlalchemy import select as _select

        from app.models.memory import Memory as _Memory

        row = db.execute(_select(_Memory).where(_Memory.id == mid)).scalar_one()
        assert row.external_status == "pending_delete"
        assert row.external_error == "MemoryClientTransientError"

    def test_sync_missing_row_raises_not_found(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        with pytest.raises(MemoryNotFound):
            memory_service.sync_memory(
                db,
                memory_client,
                user_id=owner_id,
                memory_id=uuid4(),
            )

    def test_sync_cross_user_raises_not_found(
        self, db: Session, owner_id: UUID, memory_client: FakeMemoryClient
    ) -> None:
        mid = seed_memory(user_id=owner_id, text_body="mine")
        with pytest.raises(MemoryNotFound):
            memory_service.sync_memory(
                db,
                memory_client,
                user_id=uuid4(),
                memory_id=mid,
            )
