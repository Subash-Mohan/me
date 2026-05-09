# Decisions

Append-only log of implementer judgment calls. Never edit a past entry — supersede it with a new one referencing the old.

Format:

```
## YYYY-MM-DD — <topic>
**Choice:** ...
**Why:** ...
**Alternatives considered:** ...
```

## 2026-05-09 — `memories.search_tsv` config = `'simple'`
**Choice:** The generated `tsvector` on the `memories` table uses Postgres FTS config `'simple'` (no stemming, no stopword removal).
**Why:** The local FTS path is a fallback only — Supermemory is the primary search. `'simple'` is multilingual-safe and avoids stemming surprises in personal-text journaling (e.g. `'running'` → `'run'`). If/when local FTS becomes the primary path, revisit and consider `'english'` or per-row language detection.
**Alternatives considered:** `'english'` (better English ranking, worse for non-English entries); language-detection at insert time (extra dep, more complexity for a fallback path).

## 2026-05-09 — Drop `'failed'` from `memories.external_status` v1
**Choice:** The CHECK on `external_status` allows only `('synced','unsynced','pending_delete')`. No `'failed'` terminal state.
**Why:** No code path on the inline-sync model emits `'failed'` — transient errors set `'unsynced'`, delete failures set `'pending_delete'`. Adding `'failed'` to the schema before defining the trigger condition (retry counter? operator action?) encodes a state nothing writes. Reintroduce when a retry-counter/terminal-state policy is defined.
**Alternatives considered:** Keep `'failed'` reserved for future use (rejected — adds enum value with no writer; ENUM additions are cheap when needed via a migration).

## 2026-05-09 — DB-level CHECK constraints on `memories` for hash, lat/lng
**Choice:** Migration adds four table-level CHECKs: `octet_length(content_hash) = 32`; `(location_lat IS NULL) = (location_lng IS NULL)`; `location_lat IS NULL OR location_lat BETWEEN -90 AND 90`; `location_lng IS NULL OR location_lng BETWEEN -180 AND 180`.
**Why:** Defense-in-depth at the DB boundary. Catches accidental MD5/truncated hashes (16 bytes), out-of-range coords, and unpaired lat/lng — all of which the service should already 422 on, but the DB is the last line. Cheap (no measurable write overhead at this scale).
**Alternatives considered:** Service-only validation (rejected — single failure point); CHECKs in a domain type (rejected — over-engineered for one table).

## 2026-05-09 — `Memory.search_tsv` omitted from the ORM
**Choice:** The `search_tsv` generated column lives in the migration but is NOT mapped on the `Memory` SQLAlchemy class.
**Why:** It is read only by hand-written SQL in the local-FTS fallback (planned in 05d); ORM code never touches it. Mapping a `Computed(...)` generated tsvector adds SQLAlchemy version-sensitivity and autogenerate quirks for zero benefit. If a future path needs to read it through the ORM, add it then.
**Alternatives considered:** Map with `sa.Computed(..., persisted=True)` (rejected for the reasons above); map as `server_default=FetchedValue()` (older pattern, even more brittle).
**Superseded by:** 2026-05-09 — `Memory.search_tsv` mapped with Computed.

## 2026-05-09 — `Memory.search_tsv` mapped with Computed
**Choice:** Map `search_tsv` on the `Memory` class as `Mapped[str]` with `Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True)`. The full `__table_args__` (5 CHECK constraints + 4 indexes) also moved onto the model.
**Why:** Adding `__table_args__` to mirror the migration's constraints/indexes exposed that omitting `search_tsv` from the model causes `alembic check` to flag a (false) drop. SQLAlchemy 2.x handles `Computed(..., persisted=True)` cleanly — the speculative "version risk" cited in the prior decision didn't materialise. ORM code still doesn't read or write `search_tsv`; the column is just declared so model and DB tell the same story.
**Alternatives considered:** Add an `include_object` filter in `migrations/env.py` to hide the column from autogenerate (rejected — scatters one column's special-casing into env.py); leave the drift and document it (rejected — `alembic check` is now part of our drift-detection toolbox and shouldn't be permanently red).
**Supersedes:** 2026-05-09 — `Memory.search_tsv` omitted from the ORM.

## 2026-05-09 — Local Postgres dev port moved from 5434 to 5435
**Choice:** `docker/docker-compose.yml`, the `Makefile` (`up` echo + `test-db-migrate`), `.env`, and `tests/conftest.py` now use host port `5435`.
**Why:** Port `5434` is occupied on this dev machine by an unrelated long-running container (`deployment-relational_db-1`). `5435` is free and the change is contained to local config.
**Alternatives considered:** Stop the conflicting container (rejected — affects unrelated work); make the port a configurable env var (rejected — over-engineered for a one-machine adjustment, can revisit if multiple devs hit this).

## 2026-05-09 — `MemoryClient` Protocol + `SupermemoryClient` SDK adapter
**Choice:** The vendor-agnostic abstraction is `MemoryClient` (a `typing.Protocol`). `SupermemoryClient` is the production implementation, delegating to the official `supermemory` Python SDK and translating its exceptions to a `MemoryClientError` hierarchy. `FakeMemoryClient` is the test double — also a structural impl of the Protocol. The service layer (05d) and routes (05e) take `client: MemoryClient`; they never reference the SDK or the vendor class concretely.
**Why:** The SDK is Stainless-generated, fully typed, and ships separate sync/async classes (we use only sync — no async leakage into the codebase). API drift becomes a version bump rather than a code change. The Protocol seam means swapping memory backends later is a one-class change with zero call-site churn. An earlier draft of 05c proposed a hand-rolled `httpx` wrapper; on inspection the SDK is the better choice and the abstraction (`MemoryClient`) keeps swap-out cheap.
**Alternatives considered:** Hand-rolled `httpx` wrapper (rejected — re-implements 60+ lines of plumbing the SDK ships and types correctly, and we'd own the response-shape drift); SDK with no abstraction (rejected — leaks `Supermemory` types into the service layer, makes the swap-out story expensive).

## 2026-05-09 — `MemoryClientError` hierarchy
**Choice:** Five-class hierarchy: `MemoryClientError` (base) plus `MemoryClientAuthError` (401/403), `MemoryClientNotFoundError` (404), `MemoryClientRateLimitError` (429), and `MemoryClientTransientError` (5xx, network, timeout, default for unmapped). The adapter translates the SDK's `AuthenticationError` / `PermissionDeniedError` / `NotFoundError` / `RateLimitError` / `APIConnectionError` / `APITimeoutError` / generic `APIError` into the matching subclass.
**Why:** A flat error class forces callers to inspect `.status` to distinguish a revoked key (a config bug — fallback masks it forever) from transient 5xx (graceful degrade is correct). Hierarchical errors let future operator improvements (e.g. paging on `MemoryClientAuthError`) hook in without re-parsing exception payloads. The cost is ~5 small classes.
**Alternatives considered:** Flat `MemoryClientError(status, code, message)` (rejected — see above); reuse the SDK's exception types directly in service code (rejected — leaks vendor types across the abstraction).

## 2026-05-09 — `SearchHit.doc_id: str` (not `custom_id: UUID`)
**Choice:** The `SearchHit` value type carries Supermemory's internal `document_id` (as `doc_id`). The service layer (05d) hydrates journal-entry rows via `Memory.external_id IN (:doc_ids)`.
**Why:** The Supermemory `POST /v3/search` response does not currently echo the user-supplied `customId` on hits — it returns only the vendor's internal `id`. The earlier draft of 05c assumed `custom_id` was available, which would have produced an empty hydration set in 05d. The `Memory.external_id` column already exists for exactly this mapping. If a future API revision adds `customId` to search hits, `SearchHit` gains an optional field; no breaking change.
**Alternatives considered:** Maintain a parallel `external_id → custom_id` cache in the adapter (rejected — duplicates the DB row's mapping, drifts on edit/delete); search by `metadata.custom_id` filters (rejected — extra round-trip and not necessary while `external_id` works).

## 2026-05-09 — Test-side `MemoryClient` swap via `app.dependency_overrides`
**Choice:** Tests use FastAPI's `app.dependency_overrides[get_memory_client] = lambda: fake` (mirroring the existing `get_db` override pattern) to swap in `FakeMemoryClient`. There is no env-var toggle (`MEMORY_SUPERMEMORY_FAKE` etc.) anywhere in production code.
**Why:** A production env-var branch adds a misconfiguration mode (prod accidentally sets the flag and silently goes fake). The dependency-override pattern is what the codebase already uses for `get_db` and is the FastAPI-idiomatic way. Removing the branch eliminates the failure mode entirely.
**Alternatives considered:** Env-var toggle in `get_memory_client` (rejected — see above); class-level `MemoryClient.fake_mode` flag (rejected — same global-state risk).

## 2026-05-09 — Singleton SDK client lifecycle via `lru_cache` + lifespan close
**Choice:** `app/core/deps.py:_build_memory_client(settings)` is `@lru_cache`d to size 1; `get_memory_client` returns the cached `SupermemoryClient`. `app/main.py`'s lifespan calls `shutdown_memory_client()` on shutdown to close the SDK's underlying `httpx.Client` and clear the cache.
**Why:** Per-request construction would open a fresh TCP connection pool every call (no keepalive) and leak file descriptors over time. Singleton with explicit lifespan teardown is the standard FastAPI pattern for shared HTTP clients.
**Alternatives considered:** Per-request construction (rejected — perf and FD-leak issues above); module-level singleton (rejected — tied to import order, harder to reset in tests).

## 2026-05-09 — Adapter forces `max_retries=0` on the SDK
**Choice:** `SupermemoryClient.__init__` constructs `Supermemory(..., max_retries=0)`, overriding the SDK default of `2`.
**Why:** The retry policy lives at the service layer in 05d ("never re-raise; on `MemoryClientError` set `external_status='unsynced'` and continue; the user retries via the per-row UI button"). Two layers of retry would compound — every request would take up to 3× the configured timeout before the service falls back, breaking the inline ~500ms cap.
**Alternatives considered:** Accept the SDK's default retries (rejected — see above); `max_retries=1` for transient 5xx (rejected — partial measure that still doubles worst-case latency).

## 2026-05-09 — Explicit `httpx` connection-pool limits on the Supermemory client
**Choice:** `SupermemoryClient.__init__` constructs the SDK with an injected `httpx.Client(limits=httpx.Limits(max_connections=4, max_keepalive_connections=4, keepalive_expiry=5.0))`, overriding the SDK default of `Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=5.0)`.
**Why:** This is a single-user app with inline (non-fanned-out) Supermemory calls; steady-state pool size is 1-2 sockets, so the cap is purely a ceiling. Setting it to 4 is defense-in-depth: if a future fan-out path is introduced accidentally (bulk re-sync, parallel search from the chat agent), requests queue locally on the pool instead of stampeding Supermemory's rate limit. The number is also self-documenting — a reviewer reading `max_connections=4` reads "low-volume, single-tenant," which matches the app.
**Alternatives considered:** Use SDK defaults of 100/20 (rejected — wrong signal in code review, and provides no local backpressure if fan-out gets introduced); set `max_connections=1` (rejected — too tight, would serialise even legitimate concurrent reads from a future memory-browser screen).

## 2026-05-09 — `MemoryClientPermanentError` for 4xx caller bugs
**Choice:** Added `MemoryClientPermanentError` to the `MemoryClientError` hierarchy. The adapter's `_translate` now routes any `APIStatusError` with `400 <= status < 500` (except the explicitly-mapped 401/403/404/429) to this class instead of `MemoryClientTransientError`.
**Why:** 400 (BadRequest), 409 (Conflict), and 422 (UnprocessableEntity) are caller bugs — the request shape is wrong, the document collides, validation failed. Retrying with the same payload will fail forever. Mapping them to `MemoryClientTransientError` (the class explicitly named "retry-eligible") would tell the service layer's "mark unsynced and continue" logic that the user/UI retry button might help, when it never will. Distinct class name lets future operator improvements (alarm on permanent errors, hide retry button, surface validation message) hook in without inspecting `.status`.
**Alternatives considered:** Single flat error with status code (rejected — forces every caller to inspect status to know whether retry is sensible); merge into `MemoryClientError` base directly (rejected — semantically the same as the flat error; subclass communicates intent in code-review).

## 2026-05-09 — `_build_memory_client` is parameterless
**Choice:** `app/core/deps.py`'s `_build_memory_client` takes no arguments and calls `get_settings()` inside its body. `get_memory_client` is a parameterless function that returns the cached value.
**Why:** Earlier draft had `_build_memory_client(settings: Settings)` decorated with `@lru_cache(maxsize=1)`, with `get_memory_client` injecting `settings` via `Depends(get_settings)`. But Pydantic v2 `BaseModel`/`BaseSettings` instances are unhashable by default, so `lru_cache(settings)` raises `TypeError: unhashable type: 'Settings'` on the first call. Tests passed only because every test path overrode the dep with a fake. The very first real request to a memory-using endpoint (in 05e) would have crashed. Parameterless cache + inner `get_settings()` call sidesteps the hashability issue while still amortising construction across requests.
**Alternatives considered:** Make `Settings` hashable via `model_config = ConfigDict(frozen=True)` (rejected — wider blast radius; freezing settings might break other callers that expect to mutate-in-tests); use a plain module-level singleton with `if _client is None` check (rejected — `lru_cache` is what `get_settings` already uses, consistent pattern wins).

## 2026-05-09 — `_UNSET` sentinel for memory patch semantics
**Choice:** `app/services/memory.py` defines a module-level `_UNSET = object()` sentinel; `update_memory`'s patchable kwargs default to `_UNSET`. The function checks `is _UNSET` to distinguish "field omitted" from "field provided as `None` (clear)".
**Why:** `MemoryPatch` (Pydantic) uses `field: T | None = None` for omission, but at the API boundary `model_dump(exclude_unset=True)` strips omitted fields, so the service signature only receives explicitly-provided values. The sentinel is the standard Python idiom for the same job at function-call sites (CLI calls, future agent calls) where there is no Pydantic layer.
**Alternatives considered:** Single dict argument `patch: dict[str, Any]` (rejected — loses keyword-arg call-site clarity, no IDE autocomplete on field names); `typing_extensions.Sentinel` (rejected — adds a dep for one trivial case); separate `clear_*: bool` flags per field (rejected — doubles the kwarg surface).

## 2026-05-09 — Memory service owns transaction boundary
**Choice:** `create_memory` / `update_memory` / `delete_memory` / `sync_memory` call `db.commit()` themselves. `get_memory` and `list_memories` are read-only and don't touch the transaction.
**Why:** The Supermemory side-effect must be observable before the local commit lands — if the handler did the commit and it failed (e.g. constraint violation deferred to commit), Supermemory would have a doc with no local row. Keeping commit in the service guarantees external write + local row state commit atomically. Deviates from `app/services/owner.py`, which flushes and lets the caller commit; that service has no external side-effect, so the divergence is justified by the side-effect, not by service-layer style.
**Alternatives considered:** Outbox pattern (write local + outbox row in one tx, async worker drains to Supermemory) (rejected — explicit "no daemon" decision in 05c, and overkill for single-user inline writes); commit in handler (rejected — see above).

## 2026-05-09 — `MemoryClientError` swallowed on memory writes; permanent errors emit a separate warning
**Choice:** `create_memory` / `update_memory` / `delete_memory` / `sync_memory` catch any `MemoryClientError` subclass (including `MemoryClientPermanentError`), set `external_status='unsynced'` (or `'pending_delete'` on delete), record `external_error=type(err).__name__`, and never re-raise. On `MemoryClientPermanentError` specifically, emit `log.warning("memory.external_permanent_err", op=..., memory_id=..., error_class=...)`.
**Why:** "Local writes always succeed" is the never-block-the-user rule (CLAUDE.md cross-cutting rule 5: external-API failures must never block sending or browsing of locally-persisted data). But `MemoryClientPermanentError` is a 4xx caller-bug class — retrying via `/sync` will fail for the same reason forever — so it needs a separate operator signal that's distinct from a transient blip. The warning log is that signal; user-facing behaviour stays identical.
**Alternatives considered:** Re-raise `MemoryClientPermanentError` to the API (rejected — violates the "never block local writes" rule and there's no useful action the user can take with a 422); introduce `external_status='failed'` for permanent errors (rejected for now — the 05a plan deliberately dropped `'failed'` and reintroducing it needs a retry-counter / terminal-state policy first; the warning log fills the gap until then).

## 2026-05-09 — Cursor format includes a `v` field
**Choice:** `encode_cursor` produces `base64({"v": 1, "ed": iso_date, "id": uuid_str})`. `decode_cursor` raises `MemoryValidationError` on missing version or any version other than `1`.
**Why:** Cheap forward-compat hook. If the cursor shape ever needs to evolve (e.g. add a tie-breaker beyond `(event_date, id)`, or switch to a different sort key), bumping `v` lets new cursors carry new fields while old cursors raise a clear error rather than silently truncating or returning wrong pages.
**Alternatives considered:** No version field, evolve via best-effort key probing (rejected — silent failure modes hurt long-lived clients); HMAC the cursor (rejected — single-user app, the cursor is already user-scoped server-side, tampering buys nothing).

## 2026-05-09 — `MAX_PAGE_LIMIT = 200` in the memory service
**Choice:** `app/services/memory.py` defines `MAX_PAGE_LIMIT: Final[int] = 200`. `list_memories` and `search_memories` clamp `limit` to `[1, MAX_PAGE_LIMIT]` before any query runs.
**Why:** Pydantic validation only guards the HTTP path. CLI / chat-agent / future internal callers pass values directly into the service; an unbounded `limit=100_000` would build a giant SQL `LIMIT` clause and send `100_000` to Supermemory. The clamp is defense in depth; `200` is generous for a single-user journal but small enough that no realistic call path needs more.
**Alternatives considered:** Trust callers (rejected — every non-HTTP call site would need to remember to validate); split into `LIST_MAX` / `SEARCH_MAX` (rejected — two constants for the same idea is noise); use a Pydantic-only limit (rejected — same reason as the main choice).

## 2026-05-09 — DB transaction held across the inline Supermemory call (accepted tradeoff)
**Choice:** `create_memory` (and `update_memory` after a text change) flush the local INSERT, call `client.add(...)` / `client.patch(...)`, then commit. The local DB transaction is open across the network call (≤2s per `supermemory_timeout_ms`).
**Why:** Single-user app, inline writes, one Postgres connection at a time — the lock retention has no observable effect at this scale. The alternative (commit local, then call Supermemory in a second tx) would mean a window where the local row exists with `external_status='unsynced'` even on the success path, which is more state to reason about.
**Alternatives considered:** Outbox pattern with async worker (rejected — explicitly out of scope per 05c "no retry / no daemon"); two-tx pattern as above (rejected — adds an artificial intermediate state on the happy path); shorten `supermemory_timeout_ms` to e.g. 500 (rejected — 2s already gives plenty of headroom over Supermemory p95; tighter is a different decision).

## 2026-05-09 — Memory service errors live in `_memory_errors.py` (supersedes inlining in `memory.py`)
**Choice:** `MemoryNotFound` / `MemoryDuplicate` / `MemoryValidationError` / `MemoryIdempotencyReused` are defined in `app/services/_memory_errors.py`. `memory.py` re-exports them via `__all__` so `from app.services.memory import MemoryNotFound` keeps working.
**Why:** The original layout (errors in `memory.py`, helpers in `_memory_helpers.py` importing back) created a circular import that was suppressed with `# noqa: E402` and a comment explaining the ordering trick. A dedicated errors module breaks the cycle structurally — both `memory.py` and `_memory_helpers.py` import errors from a leaf module that imports nothing project-internal.
**Alternatives considered:** Move helpers into `memory.py` (rejected — file already 580+ LOC; helpers benefit from being unit-testable in isolation); inline the error classes in `_memory_helpers.py` (rejected — error taxonomy belongs with the service surface, not pure helpers).

## 2026-05-09 — `_UNSET` is a class instance with a real type, not `object()` (supersedes the `Any`-typed signature)
**Choice:** `class _UnsetType: ...; _UNSET: Final[_UnsetType] = _UnsetType()`. `update_memory`'s patch kwargs are typed `T | None | _UnsetType`. The discriminator is `isinstance(value, _UnsetType)`.
**Why:** Earlier draft typed every patch kwarg as `Any` to keep the sentinel out of the public type. That defeats `ty check` — `update_memory(text=42)` typechecks. A nominal sentinel class restores type safety with no runtime cost and no new dependencies (rejected `typing_extensions.Sentinel` previously for being heavy; a stdlib class is lighter still).
**Alternatives considered:** Stay with `object()` and `Any` (rejected — silent typing regression on the public surface); use `typing_extensions.Sentinel` (rejected — same reason as the prior decision); use PEP 661 syntax (rejected — not stable across the type checkers in CI).

## 2026-05-09 — `IntegrityError` → `MemoryDuplicate` only fires for the content-hash unique index
**Choice:** `update_memory` inspects `exc.orig.diag.constraint_name` and only maps `ux_memories_user_content_hash` to `MemoryDuplicate`. Other constraint violations (CHECKs, FKs) re-raise as `IntegrityError` so they surface as 500s rather than misleading 409s.
**Why:** Earlier branch raised `MemoryDuplicate` whenever `text_changed=True` and *any* `IntegrityError` fired. CHECKs (`ck_memories_location_paired`, etc.) and FK violations would then have been reported as caller-side dupes, masking real bugs. Constraint name is the only stable, message-locale-independent signal psycopg exposes.
**Alternatives considered:** Match psycopg `pgcode='23505'` (rejected — narrows to "any unique violation" not "this specific index"); parse the SQLSTATE message (rejected — locale-fragile).

## 2026-05-09 — `create_memory` raises `MemoryIdempotencyReused` when the id collides with a tombstone
**Choice:** Layer-1 dedupe lookup includes soft-deleted rows. If the matching row has `deleted_at IS NOT NULL`, `create_memory` raises `MemoryIdempotencyReused` instead of attempting the INSERT (which would crash on the unconditional PK).
**Why:** Without this, a client that retries an `idempotency_id` after a delete hits an unhandled `IntegrityError` and the request 500s. Surfacing a typed domain error gives the API a clear 409-class response and tells callers to mint a new id.
**Alternatives considered:** Catch the post-INSERT `IntegrityError` and translate (rejected — pre-check is one PK lookup, the typed error path is uniform with layer-1 dedupe semantics); silently undelete the row (rejected — undelete is a policy decision the service shouldn't make).

## 2026-05-09 — `delete_memory` resets `external_status` to `'synced'` on a successful client delete
**Choice:** After a successful `client.delete`, `delete_memory` sets `row.external_status = 'synced'` and `row.external_error = None` regardless of prior status.
**Why:** Without the reset, an `unsynced` row with a populated `external_id` (a real seedable state — e.g. write succeeded then a later patch failed) keeps `external_status='unsynced'` after a successful delete. A subsequent `sync_memory` call would route through the patch branch and re-PATCH a deleted Supermemory document. Aligning with `sync_memory`'s `pending_delete` success branch (which already sets `synced`) keeps the state machine consistent: `synced` means "remote agrees with our intent", whether that intent is "row exists" or "row is gone".
**Alternatives considered:** Introduce a `tombstoned` status distinct from `synced` (rejected — adds vocabulary for no caller-visible benefit; `deleted_at IS NOT NULL` already encodes "this is gone"); leave status alone and have `sync_memory` short-circuit on soft-deleted rows whose `external_id` is unset by `delete_memory` (rejected — couples two methods through a side-channel).
