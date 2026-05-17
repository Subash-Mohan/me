# Me — agent context

A single-user, chat-first personal journaling app with a memory layer. Two screens: chat (capture + recall + reminders + image-attach) and memory browser (read/edit). Backend is Python/FastAPI + Postgres. Memory is stored and retrieved via the **Supermemory API** — no homegrown extraction/embedding pipeline.

This file is your one-stop briefing.

---

## Where to look

| Path | When to read |
|---|---|
| `Plans/phases/NN-*.md` | Always — open the one phase you're implementing. The directory is currently empty; phases are authored as work begins. |
| `DECISIONS.md` | Always — append every implementer judgment call here. Never overwrite. |

When the user says "let's start phase NN", read `CLAUDE.md` + `Plans/phases/NN-*.md` + `DECISIONS.md`. That's it.

---

## Status — what's shipped

Phases 00–04 shipped before the Supermemory pivot (2026-05-08). Their plan files were deleted in the cleanup; the behaviour lives in code + git history:

| # | What shipped |
|---|---|
| 00 | Python toolchain (`uv` / `ruff` / `ty`), project skeleton, lint/format/type-check, pre-commit |
| 01 | docker-compose Postgres, FastAPI skeleton, Alembic init |
| 02 | Sync SQLAlchemy session, fail-fast lifespan DB probe, `/healthz` round-trip |
| 03 | Data-layer conventions, Alembic `env.py` wiring (no tables yet) |
| 04 | Custom passphrase auth (single-user JWT, step-up via `X-Confirm-Passphrase`, owner created via CLI) |

Everything else (memory storage/retrieval, chat capture/recall, reminders, images, profile, deploy) is to be re-planned phase-by-phase against the Supermemory-backed approach.

---

## Tech stack

| Layer | Dev | Prod |
|---|---|---|
| Language | Python 3.12+ | same |
| API | FastAPI (sync handlers) | same |
| ORM / migrations | SQLAlchemy 2.x (sync) + Alembic | same |
| Database | Postgres in Docker | TBD |
| Auth | Custom passphrase + JWT (our own endpoints) | same |
| Memory | Supermemory API | same |
| Object storage | Local FS under `./var/images/` | TBD |
| LLM | OpenRouter (OpenAI SDK pointed at it) | same |
| Mobile client | Expo SDK 54 + RN 0.81 + Expo Router v6 + NativeWind v4 (Tailwind 3.4) in `mobile/`, pnpm workspace | same |
| Hosting | local | TBD |

Single-user app. Prod choices (DB host, storage, hosting, push) get resolved in their own phases.

---

## Project layout

```
.
├── app/
│   ├── api/            # FastAPI routers
│   ├── agents/         # chat agent + tools (empty scaffold)
│   ├── workers/        # background worker entrypoints (empty scaffold)
│   ├── services/       # cross-cutting business logic
│   ├── models/         # SQLAlchemy models
│   ├── schemas/        # Pydantic request/response schemas
│   ├── db/             # session, engine, base
│   ├── core/           # config, security, logging, deps
│   ├── cli.py          # admin CLI (e.g. create-owner)
│   └── main.py         # FastAPI app + lifespan
├── migrations/         # Alembic
├── tests/              # pytest (real Postgres, no DB mocks)
├── docker/             # Dockerfile, docker-compose.yml
├── mobile/             # Expo + RN + NativeWind client (pnpm workspace)
├── Plans/phases/       # per-phase plans (currently empty)
├── DECISIONS.md
├── package.json        # pnpm workspace root
├── pnpm-workspace.yaml
└── pyproject.toml
```

Don't invent new top-level dirs without recording the choice in `DECISIONS.md`.

---

## Cross-cutting rules — non-negotiable

These apply everywhere unless a phase file explicitly overrides them.

1. **Sync API.** FastAPI routes and the services they call are sync (`def`, `psycopg`, sync `Session`). Don't introduce `async def` in routes. If a worker is reintroduced, that's the only place `asyncio` lives.
2. **Idempotency.**
   - Client supplies a UUID per chat message; backend upserts on it.
   - Image uploads dedupe by content hash.
3. **Time / TZ.** Store everything in UTC. Mobile sends user TZ on every call. Reminders fire on local wall-clock and survive DST.
4. **Privacy.** Never log message bodies, image bytes, or passphrases — only IDs, timestamps, error types. API keys (Supermemory, OpenRouter) never leave the backend.
5. **Failure isolation (runtime).** External-API failures (Supermemory, OpenRouter) must never block sending or browsing of locally-persisted data. **Boot is a different regime:** the `lifespan` startup body fail-fasts on missing hard dependencies (DB unreachable → log + raise → process exits). Misconfiguration should crash at deploy time, not silently serve degraded responses. Retry is the orchestrator's job, not the app's.
6. **No hardcoded secrets.** Everything via env vars: `DATABASE_URL`, `JWT_SECRET`, `OPENROUTER_API_KEY`, `OPENROUTER_DEFAULT_MODEL`, `SUPERMEMORY_API_KEY`. Storage and push config get their own env vars when those phases land.

---

## Coding standards

- **Sync HTTP.** Routes, services, and DB sessions are sync. See cross-cutting rule 1.
- **Type-hinted.** Public functions are fully typed. CI runs `ty check` on `app/`.
- **Lint/format.** `ruff check` + `ruff format`. Pre-commit enforces both.
- **Migrations.** Every model change ships with an Alembic migration in the same PR. Never edit a migration that has been applied to a shared environment.
- **Tests.** pytest. Integration tests use real Postgres (operator-side `make test-db-migrate`). No DB mocks. Each endpoint has at least one happy-path integration test.
- **Logging.** Structured (`structlog`) at INFO+; never log message content, image bytes, or passphrases.
- **Errors.** Raise FastAPI `HTTPException` only at the API boundary; services raise typed domain errors.
- **Comments.** Default to none. Add only where the *why* is non-obvious.
- **Theme tokens, not raw hex.** In the mobile client, never inline hex colors in JS props (e.g. `color="#000000"` on a lucide icon, `backgroundColor: "#1A1A1A"` in a style object). Reference the shared theme: `import { colors } from "@/theme"` and use `colors.background`, `colors.foreground.secondary`, etc. The same `mobile/theme.js` is the source of truth for `mobile/tailwind.config.js`, so NativeWind classes (`bg-surface-raised`, `text-foreground-muted`) and JS-prop colors stay in lockstep. Add a new token to `mobile/theme.js` before introducing a new color.

---

## Decisions log

`DECISIONS.md` records every implementer judgment call (lib version, retry params, schema trade-off). Format:

```
## YYYY-MM-DD — <topic>
**Choice:** ...
**Why:** ...
**Alternatives considered:** ...
```

Append-only. Never edit a past entry — supersede it with a new one referencing the old. The previous `DECISIONS.md` was wiped on 2026-05-08 as part of the Supermemory pivot; rebuild it from the next decision onward.

---

## Plan workflow per chunk

1. Read this file (already loaded) + the phase file + `DECISIONS.md`.
2. If a phase file doesn't exist yet, refine the user's intent into one before coding (concrete schema, exact endpoint shapes, lib choices).
3. Implement against the phase's verification list.
4. Land migrations + tests in the same change set.
5. Append any judgment call to `DECISIONS.md`.
6. Move to the next phase only when the verification list passes.
