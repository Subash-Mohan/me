# Phase 15 — Deployment: Dockerfile, Fly.io, CI/CD, real FCM

## Goal
Production deploy: a single Docker image with `api` and `worker` entrypoints running on Fly.io, GitHub Actions for build + staging deploy, Alembic-on-deploy, and FCM wired with real credentials.

## Functional requirements
Dockerfile:
- Multi-stage build (builder + runtime); slim final image.
- One image, two entrypoints chosen via the container command:
  - `api` → `uvicorn app.main:app --host 0.0.0.0 --port 8080`
  - `worker` → `python -m app.workers.run`
- Non-root user; healthcheck calls `/healthz`.

Fly:
- `fly.toml` defines two processes (`api` and `worker`) from the same image.
- HTTP services on the `api` process; `worker` has no public ports.
- Memory/CPU sized modestly; autoscale only on `api`.
- Secrets set via `fly secrets`: every env var listed in `.env.example`.

Migrations on deploy:
- Pre-deploy step (release_command in `fly.toml`) runs `alembic upgrade head` against the prod DB before traffic shifts.
- A failed migration fails the deploy; previous version stays live.

CI/CD (GitHub Actions):
- On push to `main`: lint + type-check + test → docker build → push to Fly registry → deploy to staging.
- Manual workflow dispatch promotes the same image SHA to prod.
- Branch protections require CI green to merge.

FCM:
- Replace the phase-08 stub with a real FCM dispatcher: service account credentials via env (`FCM_CREDENTIALS_JSON`), retry on transient errors, structured success/failure logs (no message bodies).
- Per-user device token table (added in this phase if not earlier — record in `DECISIONS.md`).

Observability:
- Fly logs + a basic metrics scrape endpoint (`/metrics` Prometheus-format) on `api` and `worker`.
- Sentry (or equivalent) wired for error tracking — keys via env.

## Out of scope
- Auto-promotion to prod (always manual).
- Blue/green or canary (basic rolling deploy is fine).
- DB read replicas.

## Depends on
- 14 (Supabase ready), all earlier phases (this is the last backend phase).

## Verification
- `docker build` produces an image; running it as `api` serves `/healthz`.
- Running it as `worker` picks up an `extraction_jobs` row from the staging DB.
- `fly deploy` to staging completes; `release_command` runs migrations cleanly; `/healthz` returns 200 publicly.
- A reminder set in the staging app fires a real FCM push to a test device.
- Force a failing migration → deploy aborts and previous version remains serving traffic.

## Master-plan refs
- §11 (Deployment), §11.4 (CI/CD), §10.3 (reliability bars).
