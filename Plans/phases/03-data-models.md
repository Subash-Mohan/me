# Phase 03 — Data-layer conventions & per-phase model approach

## Goal

Establish how every later phase will add SQLAlchemy models, Pydantic schemas, and Alembic migrations. **No tables, no models, no schemas land here** — they're added in the phase that first writes to them. This phase ships only the wiring and the conventions doc that the rest of the project will follow.

## Functional requirements

1. **`migrations/env.py` wired for per-phase models.**
   - `import app.models  # noqa: F401` runs at env.py import time so any class added later auto-registers on `Base.metadata`.
   - `target_metadata = Base.metadata`.
   - `app/models/__init__.py` stays empty (or comment-only) for now; future phases append their re-exports here as they introduce model classes.

2. **Conventions documented in `DECISIONS.md`** as a single block titled "Data-layer conventions" that all model-adding phases reference. Cover at minimum:
   - **File layout.** One file per model in `app/models/<name>.py` + re-export from `app/models/__init__.py`. Pydantic schemas in `app/schemas/<name>.py` + re-export from `app/schemas/__init__.py`.
   - **Modeling style.** SQLAlchemy 2.x with `Mapped[T]` annotations and `mapped_column(...)`. Cross-table FKs use string table refs (`ForeignKey("users.id", ondelete="CASCADE")`) so files don't need cross-imports.
   - **PKs.** `BIGINT GENERATED ALWAYS AS IDENTITY` for server-derived rows. `uuid` only when offline-friendliness is needed (e.g., a mobile-supplied client ID that the server upserts on).
   - **Timestamps.** `DateTime(timezone=True)` everywhere except where naive wall-clock is required (e.g., reminders' local fire-time for DST resilience).
   - **Defaults.** `server_default=func.now()` for `created_at`. Literal server defaults via `sa.text(...)` (e.g., `sa.text("'UTC'")`, `sa.text("ARRAY[]::text[]")`).
   - **FKs.** `ON DELETE CASCADE` by default. The 24h account-purge cron drops the user; the cascade chain handles dependents. Soft-delete is UPDATE-only and triggers no cascades. `RESTRICT` only when explicitly justified in DECISIONS.md.
   - **Fixed-vocab columns.** `text` + `CHECK (col IN (...))`. No DB enums (ALTER TYPE pain). Python-side `Literal[...]` in Pydantic gives static checking.
   - **Tag-shaped columns** (lists of strings): `text[]` with GIN index. **Object-shaped**: `jsonb`.
   - **Hash columns.** `bytea`.
   - **Embedding columns.** `vector(<dim>)`. The first phase that introduces one is responsible for: installing the `pgvector` Python dep, running `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` in its migration, and pinning the dim and embedding model in DECISIONS.md.
   - **Index timing.** HNSW vector indexes are built in the same migration that creates the column when the table starts empty. Otherwise build with `CREATE INDEX CONCURRENTLY` in a separate migration.
   - **Hand-written migrations.** Migrations are hand-written when they include any of: partial indexes, functional indexes, HNSW indexes, `CHECK` constraints, vector columns, extension creation. `make revision m="..."` (`alembic revision --autogenerate`) is fine as a starting skeleton when none of those features apply.

3. **No model files. No Pydantic schemas. No Alembic revision.** The first migration (`0001_*.py`) is shipped by whichever phase first introduces a table — per the roadmap below, that's phase 04 (auth → `users`).

## Reference roadmap (orientation only — not built here)

The eventual table set (by phase 13) and the phase that's expected to introduce each. Splits may shift as phases are implemented; each phase's own spec owns the exact column shape.

| Table | Introduced by |
|---|---|
| `users` | phase 04 (auth) |
| `conversations`, `messages` | phase 06 (chat capture); `messages.id` is the mobile-supplied UUID |
| `memories`, `images`, `memory_images` | phase 05 (memory CRUD) — created together with phase 06's chat tables if 06 ships first, else here |
| `reminders` | phase 08 (chat reminder) |
| `profiles` | phase 10 (chat meta + profile) |
| `memory_embeddings`, `extraction_jobs` | phase 11 (memory pipeline extraction); `pgvector` dep + `CREATE EXTENSION` happen here |
| `facts`, `fact_sources` | phase 12 (memory pipeline consolidation); bi-temporal columns from day one |

## Out of scope

- Any actual model, schema, or migration — those are per-phase.
- Endpoints, auth flows, or agent code.

## Depends on

- 02

## Verification

- `migrations/env.py` shows `target_metadata = Base.metadata` and `import app.models  # noqa: F401`.
- `app/models/__init__.py` and `app/schemas/__init__.py` exist and are empty (or comment-only).
- `DECISIONS.md` has the "Data-layer conventions" entry described above.
- `uv run alembic current` exits 0 against the dev DB (no revisions yet — phase 04 ships `0001_*.py`).
- `uv run ruff check . && uv run ruff format --check . && uv run ty check app && uv run pytest` all green.

## Master-plan refs

- §6.2 (entries are source of truth — implies an immutable capture log; the per-phase model split must preserve that invariant once `messages`/`memories` arrive).
- §6.3 (idempotency — chat upsert via mobile-supplied UUID; informs the `messages.id` PK choice when phase 06 lands).
