# Phase 01 — Postgres in Docker + Alembic + FastAPI scaffold

## Goal
Bring up a local Postgres (with pgvector) via docker-compose, initialise Alembic, and stand up the FastAPI app with a single liveness route — DB is reachable but not yet wired into FastAPI.

## Functional requirements
- `docker/docker-compose.yml` defines a Postgres service:
  - Postgres 16+ image with pgvector extension available.
  - Port published locally (default `5432`, configurable).
  - Persistent volume for data.
  - Healthcheck.
- `make up` / `make down` (or equivalent script) to start/stop the DB.
- Alembic initialised under `migrations/`:
  - `alembic.ini` reads `DATABASE_URL` from env.
  - `env.py` is async-aware and imports a single `target_metadata` (empty for now — actual `Base` arrives in phase 02/03).
- FastAPI app:
  - `GET /healthz` returns `{"status": "ok"}` (does not touch the DB yet — DB-aware health is phase 02).
  - App reads config from env via a `Settings` object (Pydantic settings).
- `.env.example` updated with `DATABASE_URL`, `ENV` (`dev`/`test`/`prod`), `LOG_LEVEL`.
- `uvicorn app.main:app --reload` starts cleanly.
- `psql $DATABASE_URL` reaches the Docker DB and `CREATE EXTENSION IF NOT EXISTS vector;` succeeds.

## Out of scope
- No SQLAlchemy session in FastAPI yet.
- No models, no real migrations yet (only the empty Alembic baseline).
- No auth, no business endpoints.

## Depends on
- 00

## Verification
- `make up` brings Postgres healthy within 10s.
- `psql "$DATABASE_URL" -c 'SELECT 1;'` returns 1.
- `psql "$DATABASE_URL" -c 'CREATE EXTENSION IF NOT EXISTS vector;'` succeeds.
- `alembic current` runs without error (no revisions yet is fine).
- `curl localhost:8000/healthz` returns `{"status":"ok"}`.

## Master-plan refs
- §2 (Stack), §11 (Deployment, dev/staging/prod environments).
