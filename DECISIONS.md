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

---

## 2026-05-02 — Phase 02: sync session module + healthz round-trip
**Choice:** `app/db/session.py` builds a module-level sync `Engine` (`pool_pre_ping=True`, `future=True`) and `SessionLocal` (`autoflush=False`, `expire_on_commit=False`); `get_db()` is a sync `Iterator[Session]` dependency. `app/db/base.py` exposes `Base = DeclarativeBase`. `app/main.py` wires a `lifespan` async context manager whose only job is `engine.dispose()` on shutdown. `/healthz` round-trips `SELECT 1` and returns a `JSONResponse` with a symmetric body shape — `{"status":"ok","db":"ok"}` (200) or `{"status":"degraded","db":"error"}` (503).
**Why:**
- `pool_pre_ping=True`: dev-DB restarts (e.g. `make down && make up` mid-session) otherwise leave the engine's pool holding dead connections; the per-checkout `SELECT 1` is invisible at this scale and worth the resilience.
- `expire_on_commit=False`: so attributes loaded inside a request remain readable after the implicit commit at session close, which matches the response-serialization pattern every later route will use.
- `lifespan` over the deprecated `@app.on_event("startup"/"shutdown")` pair (FastAPI removed those from new examples post-0.93). Body is sync (engine.dispose); the async wrapper exists only because that's the lifespan signature.
- `JSONResponse` over `HTTPException` for the 503 path: `HTTPException` always wraps the body in `{"detail": ...}`, which would make the failure shape asymmetric with success and force every client to special-case the unwrap. `JSONResponse` returns the body verbatim — symmetric contract, less client code downstream.
- `Annotated[Session, Depends(get_db)]` rather than `db: Session = Depends(get_db)` — appeases ruff's B008 and is the FastAPI 0.95+ canonical form.
**Phase 02 deviations from `Plans/phases/02-database-fastapi-integration.md`:** The phase file predates the 2026-05-02 sync/async and pgvector decisions. Three deviations:
1. Sync session, not async — per the sync API decision above.
2. No empty Alembic baseline migration — phase 03 owns the first revision (which will create pgvector + the first tables in one shot). The phase file's "alembic upgrade head applies cleanly" verification is replaced by "alembic current exits 0 against an empty `migrations/versions/`".
3. No pgvector extension creation — deferred to phase 03's first migration per the 2026-05-02 entry above.
**Test fixture approach:** real-Postgres tests against a `me_test` database on the same docker-compose container, **not** testcontainers. `tests/conftest.py` adds a session-scoped autouse fixture that connects to the `postgres` maintenance DB and `CREATE DATABASE me_test` if absent (autocommit required). `db_engine` and `db_session` fixtures layer on top. Rationale: testcontainers' isolation buys little for a single-developer project where the dev DB is already up; revisit when CI lands (phase 15). Adds zero new dependencies.
**Test-side import ordering:** `db_engine` imports `app.db.session.engine` lazily inside the fixture so the conftest's `os.environ.setdefault("DATABASE_URL", ".../me_test")` runs first. Importing eagerly at module top would resolve `get_settings()` against whatever `DATABASE_URL` was in the shell — pointing tests at the dev `me` database silently.
**Failure-path test deferred:** `tests/test_health.py` covers only the happy path. Provoking a 503 via `TestClient` requires monkeypatching the engine to raise on checkout, which adds fixture complexity disproportionate to the value at this stage. The 503 path was verified manually (curl while the DB container is stopped) and the live result captured here: `HTTP/1.1 503` with body `{"status":"degraded","db":"error"}`. Revisit when there is non-trivial route logic to protect.
**Alternatives considered:** lazy engine construction inside `get_db` (rejected — the module-level engine is the recommended SQLAlchemy idiom and lifespan handles the only lifecycle concern); `HTTPException` for the 503 (rejected per above); per-request engine (rejected — defeats pooling); testcontainers for tests (rejected per above).

---

## 2026-05-02 — Lifespan does a fail-fast DB probe on startup
**Choice:** `app/main.py`'s lifespan now runs `SELECT 1` against the engine *before* the `yield`. On `SQLAlchemyError` it logs `startup.db_unreachable` and raises `RuntimeError("Database unreachable on startup; aborting")` — uvicorn prints `Application startup failed. Exiting.` and the process exits without opening its port. Successful probes log `startup.db_ok`. Shutdown body still calls `engine.dispose()`.
**Supersedes:** the "FastAPI app — lifespan over @app.on_event" portion of the immediately-preceding 2026-05-02 entry (Phase 02: sync session module + healthz round-trip), which described the lifespan startup body as empty.
**Why:**
- The user's call. The trade-off was named explicitly: a fail-fast probe means a flapping DB at deploy time crash-loops the API rather than letting it come up in a degraded state. They accepted that in exchange for misconfiguration / wrong-`DATABASE_URL` failing immediately at deploy time instead of being discovered when traffic arrives.
- Single probe, no internal retries. The retry layer is the orchestrator (Fly.io / k8s restart policy) — that is the standard 2026 pattern for this and avoids reinventing backoff inside the app.
- Crash log includes the underlying psycopg/SQLAlchemy traceback (chained via `raise ... from exc`) so container logs show *why* the DB was unreachable, not just *that* it was.
**Tension with CLAUDE.md §6.7 ("Failure isolation. App stays up.") and §6.2 ("LLM outages must never block sending or browsing"):** acknowledged. Those principles still hold for runtime — `/healthz` continues to return 503 (not crash) when the DB drops mid-life. The fail-fast applies only to *startup*, where the contract is "if I can't reach my hard dependency, don't claim ready." Readers of the cross-cutting rules should read them as runtime invariants; bootstrap is a different regime.
**Test impact:** `tests/test_health.py` uses `client = TestClient(app)` at module scope, which does not fire lifespan in Starlette — so the probe does not run during pytest, and the real-Postgres `me_test` database does not need to be reachable for non-DB tests. Anyone refactoring the test to `with TestClient(app) as client:` (the recommended form) must ensure the test DB is up first; the autouse `_ensure_test_database` fixture covers that.
**Alternatives considered:** log-only probe that doesn't crash (rejected by user — the whole point was crash on misconfig); no probe (rejected by user — the prior recommendation); retry-with-backoff inside lifespan (rejected — duplicates orchestrator behavior, and prolonging "starting" state during a real outage is worse than a fast crash that makes the orchestrator's restart counter visible).

---

## 2026-05-02 — Phase 02: test-DB fixtures deferred to CI
**Choice:** Phase 02 ships zero pytest fixtures or tests that touch the database. `tests/conftest.py` is reverted to just the three `os.environ.setdefault` lines that were there at the end of phase 01 (`DATABASE_URL`, `ENV`, `LOG_LEVEL`). `tests/test_smoke.py` keeps `test_truth` and `test_app_is_fastapi_instance`. `tests/test_health.py` is deleted — its assertion required a DB round-trip and there is no longer infrastructure to support it.
**Supersedes:** the "Test fixture approach" and "Test-side import ordering" portions of the 2026-05-02 entry "Phase 02: sync session module + healthz round-trip" (the autouse `_ensure_test_database` fixture, `db_engine`, `db_session`, and `test_db_session_round_trips`). Also supersedes the "Test impact" portion of the 2026-05-02 entry "Lifespan does a fail-fast DB probe on startup" — the lifespan probe still doesn't fire during pytest (because no test uses `with TestClient(...)`), but the rationale around `_ensure_test_database` is now moot because that fixture no longer exists.
**Why:**
- User's call: "we don't want to worry about test database, I'll handle this when I set up the CI." The intent is to keep the local pytest run zero-dependency (no Docker required) until CI exists, at which point CI will own DB provisioning, the fixtures, and the integration tests.
- The `/healthz` contract (200/503/symmetric body) was verified manually in this session by toggling the Docker container and curling — captured in entries above. That coverage is preserved in DECISIONS even though the automated test is gone.
- Deleting `tests/test_health.py` (vs. `@pytest.mark.skip`) was the user's explicit pick. Skip-marked tests show up in pytest output as a permanent yellow noise floor; deletion keeps the test suite honest about what's actually running.
**Re-introducing it later (CI phase, currently planned for phase 15):** restore an autouse session-scoped fixture that creates `me_test` if absent (the implementation in the superseded entry is a fine starting point), bring back `db_engine` + `db_session`, restore `test_db_session_round_trips`, restore a `tests/test_health.py` that uses `TestClient` and asserts the DB-up body. At that point also evaluate whether the lifespan startup probe should run during tests — likely yes, via `with TestClient(app) as client:` — which would require the test DB to be reachable for *every* test, not just DB-touching ones. That trade-off is for the CI phase to make.
**Alternatives considered:** keep the fixtures but `pytest.mark.skip` the DB-touching tests (rejected by user — visible noise floor); keep the fixtures but skip them via env-var gate (`SKIP_DB_TESTS=1`) (rejected — same noise plus a config knob nobody will remember); point the test DB at the dev `me` database to avoid provisioning (rejected — tests would mutate the dev DB).
