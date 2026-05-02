# Decisions

Append-only log of implementer judgment calls. Never edit a past entry — supersede it with a new one referencing the old.

---

## 2026-05-02 — Dependency manager: `uv`
**Choice:** Use `uv` (Astral) for dependency management, lockfile, and Python toolchain version pin.
**Why:** Fast resolver, single tool covers env + deps + Python version. Astral-aligned with the rest of the toolchain (`ruff`, `ty`). Standard for new Python projects in 2026.
**Alternatives considered:** Poetry (slower, larger footprint, but more conservative); pip-tools + venv (most explicit, most manual).

---

## 2026-05-02 — Lint + format: `ruff`
**Choice:** Use `ruff` for both linting and formatting (no `black`, no `flake8`, no `isort`).
**Why:** A single Rust-backed tool replaces black/flake8/isort/pyupgrade/autoflake/pydocstyle and runs orders of magnitude faster. No serious 2026 competitor; configuration lives in one block in `pyproject.toml`.
**Alternatives considered:** `black` + `ruff` (lint only) — more conservative but redundant given ruff's formatter is now stable.
**Initial rule selection:** `E, F, I, B, UP, SIM, RUF`. Line length 100. Target `py312`.

---

## 2026-05-02 — Type checker: `ty` (Astral) instead of `mypy`
**Choice:** Use `ty` as the type checker for `app/`. The phase 00 file's stated `mypy --strict` is replaced.
**Why:**
- Same authors as `ruff`/`uv` → unified Astral toolchain and editor LSP.
- 10–60× faster than mypy; fast feedback in pre-commit and editor.
- Beta as of Dec 2025, stable 1.0 targeted in 2026; Astral uses it for their own projects in production.
- Plugin gap is not a blocker here: Pydantic v2 ships native type info, and SQLAlchemy 2.x uses native `Mapped[T]` annotations (its mypy plugin is legacy for 2.x codebases).
**Alternatives considered:**
- `mypy` — most mature, best ecosystem; slower; the phase's stated default.
- `pyrefly` (Meta) — battle-tested at Instagram (20M LOC), beta, 90% spec conformance.
- `pyright` (Microsoft) — stable for years, fast, used by Pylance; Python-side config story is weaker than ty's.
**Pinned version:** `ty==0.0.34` (the version installed by `uv sync` at the time of this entry). Treat the pin tightly while ty is in beta.
**Pre-commit:** `ty` does not yet ship an official pre-commit hook repo. Wired as a `local` hook calling `uv run ty check app` so the pinned version in `pyproject.toml` stays the single source of truth.
**Fallback rule:** if `ty` blocks development before its 1.0, swap to `mypy` and add a superseding entry here. Do not silently revert.

---

## 2026-05-02 — `app/main.py` exposes a bare `FastAPI` instance
**Choice:** Phase 00's `app/main.py` instantiates `FastAPI(title="Byte Journal")` with no routes.
**Why:** Phase 01 adds the first route on top of this object. Having the instance present from day one means later phases never need to scaffold the app factory — they just register routers.
**Alternatives considered:** App-factory pattern (`def create_app() -> FastAPI`) — deferred to whenever multi-environment config makes it valuable; not needed for a single-user app yet.

---

## 2026-05-02 — Application name: "Me" (renamed from "Byte Journal")
**Choice:** Application name is "Me". Package slug `me`, FastAPI title `"Me"`, dev DB user/pass/db `me`, Supabase bucket prefix `me-images-*`.
**Why:** "Byte Journal" was the working title carried through phase 00 scaffolding and the master plan; the user confirmed the actual product name is "Me". Renaming now (one phase in, no migrations or buckets created yet) is far cheaper than after they exist.
**Supersedes:** the 2026-05-02 entry above naming the FastAPI instance `title="Byte Journal"` — read it as `title="Me"` going forward.
**Alternatives considered:** keeping the package slug as `byte-journal` for stability — rejected because nothing depends on it externally yet.

---

## 2026-05-02 — Postgres image: `pgvector/pgvector:pg16`
**Choice:** Local Postgres in `docker/docker-compose.yml` uses `pgvector/pgvector:pg16` — official Postgres 16 with pgvector pre-built (extension version 0.8.2 verified at install).
**Why:** Best dev/prod parity for the Supabase target (Supabase Postgres ships pg16+ with pgvector available). Slim image (~80MB), maintained by the pgvector team, and the de facto 2026 default for FastAPI + pgvector dev stacks.
**Alternatives considered:** `supabase/postgres` (heavier, ships extra extensions and Supabase-specific auth/role schemas we won't use because we roll our own JWT); `postgres:16` + manual `CREATE EXTENSION` (smallest base, but extension install/upgrade becomes another moving part).

---

## 2026-05-02 — Task runner: `Makefile`
**Choice:** Daily commands live in a top-level `Makefile` — `up`, `down`, `logs`, `psql`, `migrate`, `revision`, `current`, `dev`, `test`, `lint`, `format`, `typecheck`, `check`. Each target wraps `docker compose -f docker/docker-compose.yml ...` or `uv run ...`.
**Why:** Universal — `make` ships on macOS and Linux with no install. The phase 01 spec literally names `make up` / `make down`. The Makefile stays under ~30 lines for the foreseeable future. Cheat-sheet is `cat Makefile`.
**Alternatives considered:** `just` (cleaner syntax, native `.env` support, no tab-vs-spaces footgun) — rejected for now because of the extra `brew install just` step for a one-person project where `make` is sufficient. Plain `uv run` + `docker compose ...` invocations — rejected because the daily incantations are too long to retype reliably and contributors would have to reverse-engineer them.

---

## 2026-05-02 — pgvector extension creation: in the first migration that needs it
**Choice:** No `init.sql` mounted into the Postgres container. The `vector` extension will be created inside the first Alembic migration that introduces a `Vector` column (phase 03), via `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`.
**Why:**
- Single source of truth: schema (including extensions) lives in `migrations/`, not split between init scripts and migrations.
- Dev/prod parity: Supabase has no `/docker-entrypoint-initdb.d/` mechanism — init.sql only runs in dev. Putting the extension in a migration is the path that works in both environments.
- `init.sql` is non-deterministic — it only runs when the data volume is empty, which is a future footgun for "why doesn't my fresh teammate's setup match mine?".
- YAGNI: phase 01 has no Alembic revisions and no vector columns; nothing actually needs the extension installed yet.
**Phase 01 verification:** the spec's `psql ... CREATE EXTENSION IF NOT EXISTS vector;` is a one-shot manual check that proves the image *bundles* pgvector — not that the extension is auto-installed. Verified on 2026-05-02 against `pgvector/pgvector:pg16`, extension version 0.8.2.
**Alternatives considered:** mount `docker/init.sql` that creates the extension at first container start (rejected as above); ship a phase-01 Alembic revision that does *only* the extension (rejected — empty-table migrations are usually a smell).

---

## 2026-05-02 — Alembic env.py: sync + `psycopg` driver
**Choice:** Phase 01 ships a sync Alembic `env.py` (vanilla template from `alembic init migrations`, no `-t async`). `DATABASE_URL` uses the `postgresql+psycopg://...` form. `psycopg[binary]>=3.1` added to project dependencies. `asyncpg` is **not** installed.
**Why:** Migrations are sync DDL — there is no concurrency benefit to running them through an async engine. Sync env.py is shorter, has fewer moving parts, and avoids the asyncio bridge that the async template adds for what is essentially a one-shot CLI tool. Drove the URL change in `.env.example` from `postgresql+asyncpg://...` to `postgresql+psycopg://...`.
**Open question deferred to phase 02:** whether the FastAPI app uses sync (`psycopg`, single driver, simpler) or async (`asyncpg` added as a second driver, plus URL handling in Alembic) for its runtime DB sessions. Phase 01 deliberately does not commit to either — it only commits to Alembic. Phase 11 will independently choose the worker's session model.
**Alternatives considered:** async `env.py` (`alembic init -t async`) using `asyncpg` — would let one driver/URL serve both Alembic and the future async API, but locks in async for the API before phase 02's analysis; rejected to keep the decision tree small and reversible.

---

## 2026-05-02 — Logging: `structlog` from day one
**Choice:** All application logging goes through `structlog`, configured in `app/core/logging.py` and called once at `app.main` import time via `configure_logging(get_settings())`. Console renderer when `ENV=dev`; JSON renderer otherwise. Stdlib `logging` is routed through structlog's `ProcessorFormatter` so third-party libraries' logs are captured in the same stream and renderer.
**Why:** CLAUDE.md commits to "Structured (JSON) at INFO+" and the cross-cutting privacy rules ("never log message bodies or image bytes — only IDs, timestamps, error types") are easier to enforce when the logger is structured key-value and not f-stringed prose. Phases 06–11 will emit events like `agent.tool_invoked`, `extraction.failed`, `worker.entry_processed` — `structlog` is the lowest-friction way to attach context to those events. Industry-default for FastAPI in 2026.
**Alternatives considered:** stdlib `logging` only (rejected — pushes context-as-string into messages, anti-pattern for the privacy rules); stdlib + a JSON formatter like `python-json-logger` (rejected — gets you JSON output but not the bound-context model that makes the eventual phases pleasant to write).

---

## 2026-05-02 — Settings: `pydantic-settings` `BaseSettings` + `@lru_cache`
**Choice:** A single `Settings(BaseSettings)` class lives in `app/core/config.py` with `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`. Public access goes through `get_settings()` cached with `functools.lru_cache`. Phase 01 fields: `database_url: str` (required), `env: Literal["dev","test","prod"] = "dev"`, `log_level: str = "INFO"`. New env vars are added by extending the class.
**Why:** Pydantic v2 native, validated at import time, plays well with FastAPI dependency injection (we'll wire `Depends(get_settings)` in later phases when routes need config). `@lru_cache` makes the singleton implicit without a global mutable. `extra="ignore"` lets `.env` carry future vars without forcing every Settings update to be a coordinated bump.
**Alternatives considered:** plain `os.environ` reads scattered across modules (rejected — no validation, no central place to grep for "what env vars does this app need"); `dynaconf`/`environs` (heavier than needed for a single-user app).

---

## 2026-05-02 — Local Postgres host port: 5434
**Choice:** `docker/docker-compose.yml` publishes Postgres on host port **5434** (container side stays 5432). `.env.example` and `tests/conftest.py` defaults match.
**Why:** Host ports 5432 and 5433 are already bound by other Docker Postgres containers on this developer's machine (`onyx_postgres` on 5432). 5434 is the next free port and avoids forcing a teardown of pre-existing containers. The container itself still listens on 5432, so nothing inside the container changes.
**Alternatives considered:** stop the conflicting containers (rejected — they're for unrelated projects); pick a higher port like 55432 (rejected — 5434 is closer to the conventional 5432 and easier to remember).

---

## 2026-05-02 — Concurrency model: sync API, async only in the worker
**Choice:** FastAPI routes and the services they call are **sync** (`def`, `psycopg`, sync `Session`). `asyncio` is reserved for the background worker under `app/workers/`. CLAUDE.md's "Async-first. Routes, DB calls, HTTP clients are all `async`" rule is replaced by "Sync HTTP, async only in workers".
**Why:**
- The chat-send hot path writes one row and enqueues work — there's no fan-out at the request boundary that benefits from `await`.
- The work that *does* benefit from concurrency (LLM calls, embeddings, image uploads, reminder dispatch) lives in the worker, not the request path. Putting `asyncio` only where it pays its way avoids two-color codebases and threadpool/event-loop confusion in routes.
- Single driver in the API process: `psycopg` covers both Alembic and the request-path session model. Removes the open question deferred from the 2026-05-02 Alembic decision.
- Sync routes integrate with `TestClient` and synchronous fixtures with no `pytest-asyncio` ceremony.
**Resolves the open question** in the 2026-05-02 — Alembic env.py: sync + `psycopg` driver entry: the API uses sync `psycopg` too. `asyncpg` is **not** added.
**Implication for phase files:** phase 02's "Async SQLAlchemy session wired into FastAPI", phase 06's streaming chat endpoint, and any later phase that says "async route" must be re-read as sync routes + `StreamingResponse`/`SSE` over a sync iterator. Phase 11 (worker) keeps async.
**Concrete revert:** `/healthz` in `app/main.py` flipped from `async def` back to `def` to be the first example of the new convention.
**Alternatives considered:** keep async-first everywhere (rejected — paying the two-color tax for handlers that mostly do one DB write each); sync everywhere including the worker (rejected — the worker really does want concurrent LLM/embedding fan-out, async pays for itself there).
