# Phase 14 — Switch to Supabase Postgres + Supabase Storage in prod

## Goal
Point the same backend at Supabase for production: Postgres becomes the Supabase project's DB, image blobs move to Supabase Storage. No application code changes outside the storage adapter and config.

## Functional requirements
Database:
- Provision Supabase project (staging + prod). Enable `pgvector` and (if needed) `pg_cron`.
- Apply Alembic migrations against Supabase Postgres — must run identically to local.
- `DATABASE_URL` for staging/prod points at Supabase pooled connection string. Verify the SQLAlchemy async driver works with the chosen pool mode (record in `DECISIONS.md`).
- Smoke tests: create a user, post a memory, run extraction worker against the staging DB → all green.

Storage:
- Implement `SupabaseStorage` against the existing `Storage` protocol (phase 09):
  - `put` uploads blob + returns storage_ref.
  - `get_signed_url(ref, ttl_seconds)` issues a signed URL.
  - `delete` removes the blob.
- Bucket layout: one bucket per env (`byte-journal-images-staging`, `byte-journal-images-prod`). Private bucket; access only via signed URLs.
- `IMAGE_STORAGE_BACKEND=supabase` selects this implementation.
- Signed URL TTL configurable: short (e.g., 5 min) for memory-browser thumbnails, longer (e.g., 1h) for detail views — record exact values in `DECISIONS.md`.

Config:
- New env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_STORAGE_BUCKET`.
- `.env.example` updated; `.env.dev`/`.env.staging`/`.env.prod` templates documented.
- The old `LocalStorage` remains the dev default.

Auth note:
- We continue using **our own** auth endpoints (phase 04). We do **not** call Supabase Auth.

## Out of scope
- Real Fly.io deploy (phase 15).
- E2E encryption.
- Multi-region replication.

## Depends on
- 04, 09, 11

## Verification
- `alembic upgrade head` against a fresh Supabase staging project succeeds with all tables + extensions.
- Run the existing pytest integration suite with `DATABASE_URL` pointing at the staging DB and `IMAGE_STORAGE_BACKEND=supabase` — all green.
- Upload an image via `POST /images` → verify in Supabase dashboard the blob exists in the configured bucket; the returned URL 200s and expires after the TTL.
- Toggle back to `local` storage in dev → no regressions.

## Master-plan refs
- §2 (Stack — Supabase choice), §6.4 (signed URLs), §11.1 (environments).
