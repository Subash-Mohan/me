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

---

## 2026-05-02 — Phase 04 auth: passphrase + JWT, no signup, no email
**Choice:** Single-user passphrase auth. The `users` table has exactly one row (`id`, `passphrase_hash`, `created_at`, `updated_at`) — **no email column**, no other identifier. Login takes only `{passphrase}`, returns a 30-day HS256 JWT. The user is seeded at lifespan startup from `OWNER_PASSPHRASE` env using `INSERT ... WHERE NOT EXISTS` (idempotent). `OWNER_PASSPHRASE` is required only on first boot; once the row exists it's ignored, and rotating the passphrase is an out-of-band DB update for now.
**Why:**
- The app is single-user — there is no concept of "which user" to disambiguate, so the email column was dead weight that would have just confused future code.
- Passphrase rather than a static bearer token: the user wanted to type something memorable instead of pasting a secret blob.
- 30-day JWT with no refresh / no signout / no denylist: keeps the surface area minimal. Rotation = bump `JWT_SECRET` env var (invalidates all prior tokens at once).
- Step-up auth (see next entry) carries the security weight that a bearer-token leak otherwise would.
**Endpoints shipped:** `POST /auth/login`, `GET /auth/me`, `POST /auth/verify-passphrase`. **Deliberately omitted:** signup, refresh, signout, password-reset, device-ID tracking, email-validator dep.
**Dependency additions:** `argon2-cffi>=23.1` (hashing), `pyjwt>=2.8` (JWT), `slowapi>=0.1.9` (installed but not used — a custom `FailureRateLimiter` was simpler than slowapi's success-counting model). slowapi can be removed when phase 05 lands; left in for now in case a per-route limiter is wanted somewhere it isn't a failure counter.
**Alternatives considered:**
- Multi-user signup/signin per the original phase doc — rejected as ceremony for a world that doesn't exist (single user).
- Static bearer token (no passphrase) — rejected because the user wanted to type something memorable.
- "Sign in with Google" OAuth — rejected as adding an external dependency for what is, in the end, the user signing in to their own app.
- Wallet-style signed-request auth (BIP39 phrase derives ed25519 key, no shared secret on server) — discussed in detail; rejected because the user dismissed mobile-compromise threats and prioritised simplicity. Step-up auth (next entry) was the targeted defence chosen instead.

---

## 2026-05-02 — Step-up auth for destructive actions (`X-Confirm-Passphrase`)
**Choice:** A `confirm_passphrase()` FastAPI dependency in `app/core/security.py` reads the passphrase from the `X-Confirm-Passphrase` header and verifies it against the user's Argon2id hash. Phase 04 ships the dep + `POST /auth/verify-passphrase` to exercise the same primitive in body form. Future delete-style endpoints in phases 05+ (delete memory, delete entry, delete image, delete account) add `Depends(confirm_passphrase)` alongside `Depends(current_user)`.
**Why:**
- Limits the blast radius of JWT theft. A JWT pulled from a jailbroken / stolen device can read and write through the chat flow but cannot delete data, because the passphrase is never persisted on the device — it's typed at login and again at each destructive action.
- Header rather than body for the dep: the dep is reusable across any route shape (DELETE without body, etc.). `X-Confirm-Passphrase` is the conventional naming despite the deprecated `X-` prefix (RFC 6648); structlog config never logs request headers, so the passphrase stays out of normal logging.
- `verify-passphrase` endpoint exists so mobile can validate the typed passphrase *before* showing a delete-confirm UI (avoids "type wrong → watch delete fail → start over").
**Failures count toward the same rate-limit budget as `/auth/login`** (see next entry).
**Alternatives considered:**
- Body parameter on every delete endpoint — rejected, awkward for DELETE without body and forces every route to repeat the same plumbing.
- Re-issued short-lived "step-up token" model (à la sudo timeout) — rejected as overengineered for a single-user app where re-typing the passphrase is the whole point.

---

## 2026-05-02 — Auth rate limiting: in-memory `FailureRateLimiter`, no slowapi
**Choice:** A custom `FailureRateLimiter` (`app/core/rate_limit.py`) implements two sliding-window failure counters, both in-memory, both shared across `/auth/login`, `/auth/verify-passphrase`, and the `confirm_passphrase` dep:
- **Per-IP:** 5 failures per 60s window.
- **Per-user (global):** 100 failures per 24h window. (For a single-user app this is effectively the same as a global counter; left explicit in case the model ever expands.)

Successful auth does **not** increment the counter. Client IP comes from `X-Forwarded-For` (first hop) when present, else `request.client.host` — fine for Fly's edge proxy in prod and trivially testable from `TestClient` via the header in tests.
**Why:**
- slowapi was added to deps but ultimately not used: its model counts *all* requests to a route, not failures, so adapting it to "5 failures per minute" required as much custom code as just rolling a small counter (~50 lines including tests). Kept slowapi in deps for now in case a non-failure-counted limiter is wanted in a future phase; remove if still unused after phase 05.
- Sliding-window counters with a `Callable[[], float]` clock: makes the threshold and window-expiry tests fast and deterministic without sleeping.
- Pluggable via `Depends(get_auth_limiter)`: tests use a session-scoped fixture that auto-resets the singleton between tests so per-IP counters don't leak across the suite.
**Single-process scope:** the in-memory counter only protects one process's traffic. When Fly machines scale beyond one, we'll need a Redis or DB-backed counter. Not worth optimising for now — flagged here so we don't forget.
**Alternatives considered:**
- slowapi's `Limiter.limit()` with a custom storage backend — rejected as more code for a worse fit (success-counting model).
- Redis-backed counter from day one — rejected, single-process is the deployment shape for now.
- Per-route limits (different threshold per endpoint) — rejected, the budget is shared on purpose so an attacker can't burn through the budget on one endpoint and try the others.

---

## 2026-05-02 — Phase 04 auth: drop the rate limiter
**Choice:** Remove `app/core/rate_limit.py`, the `FailureRateLimiter` integration in `/auth/login`, `/auth/verify-passphrase`, and `confirm_passphrase`, the autouse reset fixture in `tests/conftest.py`, the `slowapi` dependency, and the rate-limit test files (`tests/unit/test_rate_limit.py`, `tests/api/test_auth_rate_limit.py`).
**Supersedes:** the immediately-preceding 2026-05-02 entry "Auth rate limiting: in-memory `FailureRateLimiter`, no slowapi".
**Why:**
- User's call: "for single user app it's overkill." For a single-user app the threat model that rate limiting addresses (online password spray) doesn't apply in any meaningful way — the only legitimate caller is the user themselves, and the passphrase entropy + Argon2id cost already make brute force infeasible at any plausible request rate.
- Real DDoS protection lives at Fly's edge proxy in prod, not in-process. Keeping in-app rate limiting "just in case" was carrying ~150 lines of code and an autouse fixture for no real defensive value.
- Failed auth events are still logged (`auth.login_fail` / `auth.verify_fail` with IP) so anomaly detection remains possible via log search.
**What was kept:** `client_ip()` extractor in `app/core/security.py` (still useful for log enrichment), all auth event logging.
**Re-introducing it later:** the prior commit (visible in git history) has the full `FailureRateLimiter` implementation and tests; restore from there if a future deployment shape (e.g. exposing the API more broadly than a single mobile client) makes it relevant again.
**Alternatives considered:** keep the limiter but raise thresholds (rejected — same code, same fixture, same complexity, no behaviour worth keeping); only remove the per-user counter and keep per-IP (rejected — both are equally overkill at this scale).

---

## 2026-05-02 — Owner created via CLI, not via env+lifespan
**Choice:** The owner user is created out-of-band via a small CLI:

```
uv run python -m app.cli create-owner            # prompts twice with no echo (getpass)
uv run python -m app.cli create-owner "phrase"   # arg form (avoid in shell history)
```

Lifespan no longer seeds anything; it just runs the DB-reachability probe (per the phase-02 entry). `OWNER_PASSPHRASE` is removed from `Settings`, `.env.example`, and `tests/conftest.py`. The service layer keeps a single `create_owner_user(db, passphrase) -> User` that raises `OwnerAlreadyExistsError` if a user already exists and `EmptyPassphraseError` for empty input. The previous `ensure_owner_user` (idempotent variant) was deleted — tests use `create_owner_user` after the `db` fixture's truncate, which is always a clean slate.

**Supersedes:** the "Lifespan addition" portion of "Phase 04 auth: passphrase + JWT, no signup, no email" above (the part that described `ensure_owner_user(session, settings.owner_passphrase.get_secret_value())` running inside the lifespan after the DB probe). Also removes the four `tests/api/test_lifespan.py` tests that exercised that seeding behaviour.

**Why:**
- User's call: "i don't want to put the paraphrase in env." Putting the passphrase in `OWNER_PASSPHRASE` meant it lived in `.env`, in the deploy environment, and in any process inspector that could read env vars — exactly where a long-lived secret shouldn't sit.
- The CLI accepts the passphrase as a positional arg (convenient for one-shot setup) **or** prompts via `getpass` (no shell history, no echo). The prompt path requires a second confirmation entry to catch typos.
- Exit codes are meaningful: `0` success, `1` owner already exists, `2` invalid input (empty passphrase or mismatched prompts) — so wrapper scripts and CI can branch on them cleanly.
- Service layer cleanup: collapsing `ensure_owner_user` + `create_owner_user` into a single strict function removed the "two functions doing almost the same thing" smell. Tests don't need the idempotent variant because the `db` fixture truncates before each test.

**Operational note:** Rotation is not yet a CLI command — for now, drop the user row directly (`TRUNCATE users RESTART IDENTITY`, or `DELETE FROM users WHERE id = ...`) and re-run `create-owner`. A `rotate-passphrase` subcommand can be added when the need is concrete; the cost of building it speculatively isn't justified yet.

**Alternatives considered:**
- Keep env-driven seeding but only on first boot (rejected — passphrase still has to land in the env at least once, defeating the point).
- Always-prompt CLI (no positional arg) — rejected, would force a TTY for what may be a non-interactive deploy step (e.g. `fly ssh console -C ...`).
- Two CLI commands (`create-owner` strict + `rotate-passphrase` for replace) — deferred; one command covers the immediate need.

---

## 2026-05-02 — Test infrastructure: minimal conftest + per-module reset
**Choice:** `tests/conftest.py` shrinks to env defaults + a `db` fixture (just yields a `SessionLocal()`) + a `client` fixture (TestClient with `get_db` override). It no longer creates `me_test`, no longer applies migrations, no longer truncates between tests. Those concerns split into:

- **Operator-side DB lifecycle** — three new Makefile targets (`test-db-create`, `test-db-migrate`, `test-db-reset`). Operator workflow is `make up && make test-db-migrate && make test`; re-run `test-db-migrate` after any new Alembic revision. The migrate target must pass a dummy `JWT_SECRET` because `migrations/env.py` imports `app.models.user`, which transitively loads `Settings`.
- **Per-module reset** — `tests/_db.py` exposes `reset_db()` and `seed_owner()`. Each test module that touches the DB declares one autouse module-scoped fixture: `_reset` (truncate only) or `_setup` (truncate + seed). Tests inside a module share state and run in source order.
- **`_test`-suffix tripwire** — moved out of conftest into `reset_db()` itself. If `DATABASE_URL` points at any DB whose name doesn't end in `_test`, the assertion fails on the first DB-touching test and aborts with a clear error rather than truncating production-adjacent data.

**Test files reorganized along the "starts empty" / "starts seeded" axis:**

| File | Module fixture | Purpose |
|---|---|---|
| `tests/api/test_auth_unauthenticated.py` (new) | `_reset` | All auth-surface tests that need an empty `users` table |
| `tests/api/test_auth_authenticated.py` (new) | `_setup` (seeds owner) | All auth-surface tests that need an existing user |
| `tests/api/test_auth_no_log_leak.py` | `_setup` (seeds owner + bumps log level to INFO) | Log-redaction tests |
| `tests/api/test_owner.py` | `_reset` | `create_owner_user` semantics; tests ordered to accumulate state |
| `tests/api/test_cli.py` | `_reset` | CLI subcommand tests; ordered the same way |
| `tests/unit/test_cli_prompt.py` (new) | none (pure functions) | Covers `_read_passphrase_interactively` with monkeypatched `getpass` |

Files deleted: `tests/api/test_auth_login.py`, `tests/api/test_auth_me.py`, `tests/api/test_auth_verify.py` (their tests redistribute into the two new state-axis files).

One previously-existing integration test was dropped: `test_create_owner_via_cli_prompts_when_arg_omitted`. With module-scope reset, it would have created a second owner via prompt-mode, which conflicts with the prior `test_inserts_user_via_arg` having already created one. The lost coverage is recovered by the two unit tests in `tests/unit/test_cli_prompt.py`, which exercise the prompt helper directly without DB involvement.

**Supersedes:** the "Test-DB fixture (supersedes phase-02 deferral)" section of the "Phase 04 auth: passphrase + JWT, no signup, no email" entry above (the part that described the autouse session-scoped `_ensure_test_database`, `_apply_migrations`, and per-test TRUNCATE in conftest). The phase-02 deferral entry remains relevant for the historical context, but the implementation it predicted is now superseded by this entry.

**Why:**
- User's call: "lets not do things in conftest, lets assume app is currently running, ket the conftest just returns the db session for tests or whatever industry standard is" — the per-test TRUNCATE + autouse migrations in conftest were doing too much; the operator-side Makefile + per-module reset is the more standard split (DB lifecycle outside test code, isolation strategy declared by each test module).
- Module-scoped reset (rather than function-scoped) was the user's specific choice when offered the trade-off. It's faster (one TRUNCATE per module instead of per test) at the cost of requiring tests inside a module to coexist. The reorganization above puts each test in a module whose starting state matches its needs.
- Test runtime: 1.6s → 1.0s on the local machine (43 tests). Modest absolute saving, will compound as the suite grows.

**Known constraints with module-scope reset:**
- Tests within a module share state and rely on execution order. pytest runs tests in source order by default; we depend on that. If anyone introduces test-ordering randomization (`pytest-randomly`), the `test_owner.py` and `test_cli.py` modules will fail. Document this if/when CI lands.
- Adding a new test that needs a different starting state than its module is a signal to either reorder or split the file, not to insert an ad-hoc reset.

**Alternatives considered:**
- Function-scoped reset implemented via per-module fixtures (each test still gets clean state, fixture just lives next to the tests instead of in conftest) — rejected by user in favour of true per-module sharing.
- Transaction-rollback-per-test (savepoints + connection-bound session) — rejected, breaks because `/auth/login` and several other paths call `.commit()`; making it work requires a "join the test transaction" hook that's significantly more code than module-scope reset.
- Keep the autouse DB-lifecycle fixtures but split out the truncate — rejected, conftest still owns the test DB existence and schema, which the user explicitly didn't want.
