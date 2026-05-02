# Me — agent context

A single-user, chat-first personal journaling app with a memory layer. Two screens: chat (capture + recall + reminders + image-attach) and memory browser (read/edit). Backend is Python/FastAPI + Postgres + a background worker.

This file is your one-stop briefing. **Do not open the master plan unless a phase file explicitly points you to a section.**

---

## Where to look

| Path | When to read |
|---|---|
| `Plans/phases/NN-*.md` | Always — open the one phase you're implementing. |
| `Plans/Personal Memory Layer Options.md` | Only if a phase file references a specific `§X.Y`. |
| `personal_memory_layer_guide.pdf` | Only before phases 11–13 (memory pipeline). |
| `DECISIONS.md` | Always — append every implementer judgment call here. Never overwrite. |

When the user says "let's start phase NN", read `CLAUDE.md` + `Plans/phases/NN-*.md` + `DECISIONS.md`. That's it.

---

## Phase index

| # | File | What ships |
|---|---|---|
| 00 | `00-python-env.md` | Python toolchain, project skeleton, lint/format/type-check tooling |
| 01 | `01-postgres-docker-and-fastapi-init.md` | docker-compose Postgres+pgvector, FastAPI skeleton, Alembic init |
| 02 | `02-database-fastapi-integration.md` | Async SQLAlchemy session wired into FastAPI, DB-backed health route |
| 03 | `03-data-models.md` | All SQLAlchemy models + Pydantic schemas + first table-creation migration |
| 04 | `04-auth-endpoints.md` | Custom signup/signin/refresh/me with JWT |
| 05 | `05-memory-endpoints.md` | Memory list / detail / edit / delete |
| 06 | `06-chat-capture.md` | Streaming chat endpoint, capture-only agent, `save_memory` tool |
| 07 | `07-chat-recall.md` | Recall intent + search tools (tsvector first, vector after phase 11) |
| 08 | `08-chat-reminder.md` | Reminder intent + scheduling job + FCM dispatch (stub) |
| 09 | `09-chat-image-attach.md` | Image upload + image-attach intent + image-bearing capture |
| 10 | `10-chat-meta-and-profile.md` | Meta intent, profile + settings + export + delete-account endpoints |
| 11 | `11-memory-pipeline-extraction.md` | Background worker, embeddings, fact extraction |
| 12 | `12-memory-pipeline-consolidation.md` | Bi-temporal facts, ADD/UPDATE/DELETE/NOOP, reprocess-all |
| 13 | `13-standing-user-profile.md` | Weekly profile regeneration job |
| 14 | `14-supabase-prod-migration.md` | Switch to Supabase Postgres + Storage in prod |
| 15 | `15-deployment-fly-io.md` | Dockerfile, fly.toml, CI/CD, real FCM |
| 16 | `16-mobile-stub.md` | Placeholder for React Native plans (deferred) |

---

## Tech stack — dev vs prod

| Layer | Dev | Prod |
|---|---|---|
| Language | Python 3.12+ | same |
| API | FastAPI (async) | same |
| ORM / migrations | SQLAlchemy 2.x async + Alembic | same |
| Database | Postgres-in-Docker (with pgvector) | Supabase Postgres (with pgvector) |
| Auth | Custom JWT (our own endpoints) | same — does **not** use Supabase Auth |
| Object storage | Local FS under `./var/images/` | Supabase Storage (signed URLs) |
| LLM | OpenRouter (OpenAI SDK pointed at it) | same |
| Push | FCM stubbed (logs only) | FCM real credentials |
| Hosting | local | Fly.io |
| Scheduler | `pg_cron` if available, else APScheduler | `pg_cron` |

Single Docker image, two entrypoints: `api` (FastAPI/uvicorn) and `worker` (background worker).

The same SQLAlchemy code runs against both local Postgres and Supabase Postgres — Supabase is just managed Postgres underneath. Only config and the storage adapter change between environments.

---

## Project layout

```
.
├── app/
│   ├── api/            # FastAPI routers (auth, memories, chat, profile, ...)
│   ├── agents/         # chat agent + tools (save_memory, search_facts, ...)
│   ├── workers/        # background worker entrypoints + jobs
│   ├── services/       # cross-cutting business logic
│   ├── models/         # SQLAlchemy models
│   ├── schemas/        # Pydantic request/response schemas
│   ├── db/             # session, engine, base
│   ├── core/           # config, security, logging, deps
│   └── main.py         # FastAPI app factory
├── migrations/         # Alembic
├── tests/              # pytest (real Postgres, no DB mocks)
├── docker/             # Dockerfile, docker-compose.yml
├── Plans/              # master plan + phases/
├── DECISIONS.md
└── pyproject.toml
```

Don't invent new top-level dirs without recording the choice in `DECISIONS.md`.

---

## Cross-cutting rules — non-negotiable

These come from the master plan §6. Phase files do not repeat them; they apply everywhere.

1. **Source of truth = `entries` table.** One row per chat turn. Memories, facts, embeddings, profile, image references are all derived and rebuildable. Build "reprocess all entries" from day one (phase 12).
2. **Sync vs async boundary.** The chat send must return as soon as the message row is written (< 200ms). Intent classification, fact extraction, embeddings, image upload, profile regeneration, reminder dispatch are async. Memory CRUD never calls an LLM. **LLM outages must never block sending or browsing.**
3. **Idempotency.**
   - Client supplies a UUID per chat message; backend upserts on it.
   - Image uploads dedupe by content hash.
   - Re-running extraction on an entry must not duplicate facts.
4. **Time / TZ.** Store everything in UTC. Mobile sends user TZ on every call. Reminders fire on local wall-clock and survive DST.
5. **Privacy.** Never log message bodies or image bytes — only IDs, timestamps, error types. Image URLs are short-lived signed URLs. The OpenRouter API key never leaves the backend.
6. **Rate limiting.** Per-user soft daily LLM budget (default 200 calls/day). Over budget = degrade to a cheaper model, never hard-fail. Extraction is unlimited (cheap, async).
7. **Failure isolation.** Extraction failures never affect browse or capture. After 5 retries an entry is marked `extraction_failed` and surfaced in a "needs attention" list.
8. **No hardcoded secrets.** Everything via env vars: `DATABASE_URL`, `JWT_SECRET`, `OPENROUTER_API_KEY`, `OPENROUTER_DEFAULT_MODEL`, `FCM_SERVER_KEY`, `IMAGE_STORAGE_BACKEND` (`local` | `supabase`), `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.

---

## Coding standards

- **Async-first.** Routes, DB calls, HTTP clients are all `async`. No sync DB sessions.
- **Type-hinted.** Public functions are fully typed. CI runs `ty check` on `app/` (replaces mypy — see `DECISIONS.md` 2026-05-02).
- **Lint/format.** `ruff check` + `ruff format`. Pre-commit enforces both.
- **Migrations.** Every model change ships with an Alembic migration in the same PR. Never edit a migration that has been applied to a shared environment.
- **Tests.** pytest. Integration tests use a real Postgres test container (testcontainers-python or compose). No DB mocks. Each endpoint has at least one happy-path integration test.
- **Logging.** Structured (JSON) at INFO+; never log message content or image bytes.
- **Errors.** Raise FastAPI `HTTPException` only at the API boundary; services raise typed domain errors.
- **Comments.** Default to none. Add only where the *why* is non-obvious.

---

## Decisions log

`DECISIONS.md` records every implementer judgment call (lib version, retry params, embedding model id, schema trade-off). Format:

```
## YYYY-MM-DD — <topic>
**Choice:** ...
**Why:** ...
**Alternatives considered:** ...
```

Append-only. Never edit a past entry — supersede it with a new one referencing the old.

---

## Plan workflow per chunk

1. Read this file (already loaded) + the phase file + `DECISIONS.md`.
2. If the phase file is still high-level, refine it with the user (concrete schema, exact endpoint shapes, lib choices) before coding.
3. Implement against the phase's verification list.
4. Land migrations + tests in the same change set.
5. Append any judgment call to `DECISIONS.md`.
6. Move to the next phase only when the verification list passes.
