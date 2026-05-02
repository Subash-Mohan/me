# Phase 03 — Data models & first table-creation migration

## Goal
Define every SQLAlchemy model and Pydantic schema the backend will use, plus the first migration that creates all tables. No endpoints in this phase — pure data layer.

## Functional requirements
Tables (column lists are intentionally loose — refine when implementing):

- `users` — id, email (unique), password_hash, created_at, model_preference, daily_llm_budget, timezone.
- `conversations` — id, user_id, title, created_at, last_message_at.
- `messages` — id, conversation_id, user_id, client_uuid (unique per user — idempotency), role (user/assistant/tool), content, created_at, intent (nullable until classified).
- `entries` — id, user_id, message_id (source — **source of truth** for memories), text, event_date, created_at, tz, mood (nullable), tags (jsonb).
- `memories` — id, user_id, entry_id (1:1), text, mood, tags, event_date, created_at, deleted_at.
- `images` — id, user_id, content_hash (unique per user — dedup), storage_ref, mime, width, height, bytes, created_at.
- `memory_images` — memory_id, image_id, position (M:N order-preserving join).
- `facts` — id, user_id, text, entities (jsonb), category, confidence, valid_at, invalid_at, created_at, expired_at, embedding (pgvector). Bi-temporal columns present from day one even if unused until phase 12.
- `fact_sources` — fact_id, entry_id (one fact may derive from many entries).
- `entry_embeddings` — entry_id, embedding (pgvector). Separate table so the entry row stays small.
- `reminders` — id, user_id, message, fire_at_utc, fire_at_local, tz, recurrence (none/daily/weekly), status (pending/sent/snoozed/cancelled), next_fire_at, created_at.
- `profiles` — user_id (PK), text, regenerated_at.
- `extraction_jobs` — id, entry_id, status (pending/running/done/failed), attempts, last_error, created_at, updated_at.

Plus:
- Pydantic schemas under `app/schemas/` mirroring create/update/read shapes for each model that any endpoint will expose later.
- One Alembic migration (`0001_initial.py`) creates all tables, indexes, foreign keys, and `CREATE EXTENSION vector` if not present.
- Useful indexes: `messages(client_uuid, user_id)` unique, `memories(user_id, event_date desc)`, `entries(user_id, event_date desc)`, `facts(user_id, valid_at, invalid_at)`, `reminders(status, next_fire_at)`, ivfflat/hnsw on `facts.embedding` and `entry_embeddings.embedding` (deferred index build is fine).
- ON DELETE behaviour respects "memory deletion invalidates derived facts" (cascade or trigger — record choice in `DECISIONS.md`).

## Out of scope
- No endpoints, no auth flows, no agent tools yet.
- No data seeding.

## Depends on
- 02

## Verification
- `alembic upgrade head` creates all tables on a fresh DB.
- `alembic downgrade base && alembic upgrade head` round-trips cleanly.
- `\dt` in psql lists every table above.
- `\d facts` shows `embedding vector(...)` and bi-temporal columns.
- pytest fixture can insert a user, a message, an entry, a memory, an image and read them back through SQLAlchemy.

## Master-plan refs
- §4.4 (memory pipeline data shape), §6.2 (entries = source of truth), §6.3 (idempotency keys).
