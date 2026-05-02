# Phase 02 — Wire Postgres into FastAPI

## Goal
Async SQLAlchemy session is available as a FastAPI dependency, the health route round-trips the DB, and the first (empty) Alembic revision is applied successfully.

## Functional requirements
- `app/db/session.py` provides:
  - An async engine built from `DATABASE_URL`.
  - An `async_sessionmaker` and a `get_db()` FastAPI dependency that yields an `AsyncSession`.
  - A declarative `Base` re-exported from `app/db/base.py`.
- App lifecycle hooks open and dispose the engine cleanly on startup/shutdown.
- `GET /healthz` upgraded to:
  - Acquire a session via the dependency.
  - Run `SELECT 1`.
  - Return `{"status":"ok","db":"ok"}` — or 503 with `db:"error"` if the round-trip fails.
- First Alembic revision created (empty — just establishes baseline) and applied via `alembic upgrade head`.
- pytest fixtures:
  - `db_engine` and `db_session` fixtures using a real Postgres (testcontainers or an `ENV=test` schema). No mocks.
  - One smoke test: a session can `SELECT 1`.
- `pgvector` extension is created automatically on first migration (or via an idempotent helper).

## Out of scope
- No domain models yet — they're added per-phase from phase 04 onwards. Phase 03 only sets data-layer conventions and wires `env.py`.
- No auth, no real endpoints.

## Depends on
- 00, 01

## Verification
- `alembic upgrade head` applies cleanly on a fresh DB.
- `curl localhost:8000/healthz` returns `db:"ok"`.
- Stop the DB → same call returns 503 with `db:"error"`. App stays up.
- `pytest -k smoke` runs the session smoke test green.

## Master-plan refs
- §6.1 (sync/async boundary — health must not depend on LLM).
