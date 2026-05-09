# Decisions

Non-obvious implementer choices that aren't visible from reading the code. Each entry: the choice + the why. Future additions are append-only — supersede a past entry by adding a new dated one rather than editing in place.

> Consolidated 2026-05-09 from a longer per-decision log: superseded and one-off operational entries dropped, related entries merged. Original history in git.

## Schema & DB

### `memories.search_tsv` uses Postgres `'simple'` config (not `'english'`)
Local FTS is the fallback only — Supermemory is the primary search. `'simple'` is multilingual-safe and avoids stemming surprises in personal text. Revisit if local FTS becomes the primary path.

### `memories.external_status` enum is `('synced','unsynced','pending_delete')` only
No `'failed'` terminal state in v1: nothing on the inline-sync model emits it. Reintroduce when a retry-counter / terminal-state policy is defined.

### DB-level CHECK constraints on `memories`
Defense-in-depth at the DB boundary: hash length (32 bytes), lat/lng pairing, lat/lng range, external_status enum. The service should already 422 on these; the DB is the last line.

### `Memory.search_tsv` is mapped with `Computed(...)` despite the ORM not reading it
Without the mapping, `alembic check` flags a false drop because `__table_args__` mirrors the migration's constraints/indexes. SQLAlchemy 2.x handles `Computed(persisted=True)` cleanly.

## Memory client (vendor abstraction)

### `MemoryClient` Protocol + `SupermemoryClient` SDK adapter
Vendor-agnostic Protocol; production impl wraps the official `supermemory` SDK (sync only — no async leakage); test impl is `FakeMemoryClient`. Service and HTTP layers take `client: MemoryClient` and never reference vendor types. Swapping backends = one new class.

### `MemoryClientError` hierarchy (5 classes)
Base + `Auth` (401/403), `NotFound` (404), `RateLimit` (429), `Permanent` (other 4xx — caller bug, retry won't help), `Transient` (5xx/network/timeout, default for unmapped). Lets future operator hooks distinguish "my config is broken" from "transient blip" without parsing exception payloads.

### `SearchHit.doc_id` is the SDK's `document_id`, not our `customId`
Supermemory's search response does not echo `customId` — only the vendor's internal id. Service hydrates rows via `Memory.external_id IN (:doc_ids)`.

### Test swap is via FastAPI `dependency_overrides`, not an env-var toggle
A production env-var branch would be a misconfiguration mode (prod silently goes fake). Mirrors the existing `get_db` override pattern.

### Singleton SDK client via `lru_cache` + lifespan close
`get_memory_client` returns the cached `SupermemoryClient`; lifespan teardown closes the underlying `httpx.Client` and clears the cache. Per-request construction would leak FDs and lose keepalive.

### `_build_memory_client` is parameterless
Pydantic v2 `Settings` is unhashable, so `lru_cache` keyed on `Settings` raises `TypeError` on first real call. Tests masked this because every path overrode the dep.

### SDK `max_retries=0`; explicit `httpx` connection limits = 4
Retry policy lives at the service layer (mark unsynced + manual retry). SDK retries would compound, breaking the inline ~2s cap. Connection cap is defense-in-depth: if a future fan-out path is introduced accidentally, requests queue locally instead of stampeding.

## Service layer

### `_UNSET` sentinel for `update_memory` patch semantics
`class _UnsetType: ...; _UNSET = _UnsetType()`. Patch kwargs typed as `T | None | _UnsetType`. Distinguishes "field omitted" (don't touch) from "field provided as `None`" (clear, where the column is nullable). A nominal class beats `object()` because `ty check` then keeps the public type honest.

### Memory service owns the transaction boundary
`create_memory` / `update_memory` / `delete_memory` / `sync_memory` call `db.commit()` themselves. The Supermemory side-effect must be observable BEFORE the local commit lands — otherwise a constraint violation at commit would leave a Supermemory doc with no local row. Deviates from `app/services/owner.py` (which has no external side effect).

### `MemoryClientError` is swallowed on memory writes
External-API failures must never block local writes (CLAUDE.md cross-cutting rule 5). The row persists with `external_status='unsynced'` (or `'pending_delete'`) and `external_error=type(err).__name__`. `MemoryClientPermanentError` additionally emits `log.warning("memory.external_permanent_err", ...)` because retrying a 4xx will fail forever.

### DB transaction held across the inline Supermemory call (≤2s)
Single-user, inline writes — lock retention is invisible at this scale. The two-tx alternative (commit local first, call Supermemory second) would create a window where every successful write briefly looks `unsynced` — more state to reason about for no benefit.

### `MAX_PAGE_LIMIT = 200`, clamped at the service layer
Pydantic only guards the HTTP path. CLI / agent / future internal callers pass `limit` directly; an unbounded value would build a giant SQL `LIMIT` and ship it to Supermemory.

### `IntegrityError → MemoryDuplicate` only fires for `ux_memories_user_content_hash`
`update_memory` inspects `exc.orig.diag.constraint_name`. Other constraint violations (CHECKs, FKs) re-raise as `IntegrityError` (→ 500). Earlier branch raised `MemoryDuplicate` for any `IntegrityError`, which masked real bugs as caller-side dupes.

### `create_memory` raises `MemoryIdempotencyReused` when `idempotency_id` collides with a tombstone
Without the pre-check, a client retrying after a delete would crash on the unconditional PK constraint. Surfacing a typed error gives the API a clean 409.

### `delete_memory` resets `external_status='synced'` on a successful client delete
`'synced'` means "remote agrees with our intent" — whether that intent is "row exists" or "row is gone". Without the reset, a previously-`unsynced` row with a populated `external_id` would later re-PATCH a deleted Supermemory document via `sync_memory`.

### Service errors live in `app/services/_memory_errors.py`
Breaks the circular import that emerged when `_memory_helpers.py` and `memory.py` both wanted to raise the same errors.

## API / HTTP layer

### Memory `id` is Supermemory's `customId`
Local PK doubles as both the cross-system handle and the layer-1 idempotency key (`create_memory(idempotency_id=...)` stores it as `id`). One identifier, two roles, fewer moving parts.

### Local Postgres is source of truth; Supermemory is a derived index
Reads (list, detail) go to Postgres exclusively. Search prefers Supermemory but falls back to local FTS on any client error. Inverting would couple basic read/write to an external service.

### Both dedupe layers in `create_memory` are silent on hit
Layer-1 (idempotency UUID) and layer-2 (canonical content hash) both return the existing row with status `201`, never 409. Idempotency exists so callers can retry safely; a 409 forces every caller to special-case "I already created this".

### Soft-delete local, hard-delete remote; tombstones never purged in v1
Local soft-delete enables idempotent re-deletes, supports the partial unique index that excludes deleted rows from content-hash dedupe, and keeps a future "trash bin" feature available. Hard-delete remote keeps Supermemory's index lean.

### Sync is inline + per-memory manual retry; no cron, no daemon, no outbox
Outbox/worker is the orthodox answer for async write reliability — but it brings a process to monitor, queue tuning, and poison-message handling. For a single-user app where the user is right there with a retry button, the trade-off doesn't justify the operational surface.

### Container tags are `user_<owner_uuid_no_dashes>` only (no `kind_*` in v1)
The single user-scoped tag makes search filterable to one user's data. Per-category tags need a stable taxonomy that doesn't yet exist.

### Cursor format is opaque base64 with a `v` field
`encode_cursor` returns base64 of `{"v": 1, "ed": iso_date, "id": uuid_str}`. `decode_cursor` raises `MemoryValidationError` on missing/unknown version. Forward-compat hook for sort-key evolution.

### `MemoryPatch` rejects `null` for `text`, `event_date`, `event_tz`
These columns are NOT NULL in the DB and have no "clear" semantics. A `model_validator` raises 422 if any of them is explicitly set to `null`; field omission still works (Pydantic exposes it via `model_fields_set`).

### Step-up DELETE returns 401 (not 403)
The user IS authenticated (JWT valid); they failed elevation. 401 keeps every "credential failed" surface speaking the same dialect as `_INVALID_CREDS` in the auth router.

## Logging

### `structlog` `cache_logger_on_first_use=False`
With caching on, a logger created at module import (when conftest sets `LOG_LEVEL=WARNING`) keeps its WARNING filter forever — a runtime `LOG_LEVEL` flip has no effect on existing loggers, and the privacy-guard test would pass vacuously. Disabling the cache makes `configure_logging` actually reconfigure live loggers. Per-call overhead is unmeasurable at this scale.

## 2026-05-09 — `openai-agents` floor pin
**Choice:** `openai-agents>=0.17` (resolves to 0.17.0).
**Why:** Matches established pin style (`supermemory>=3.39.0`, `pytest-httpx>=0.36.2`). The originally-drafted floor of `>=0.0.1` was effectively unpinned and would drift silently on future `uv lock --upgrade`.
**Alternatives considered:** `>=0.0.1` (too loose); `==0.17.0` (stricter than the rest of the file, no project-wide reason to enforce here).

## 2026-05-09 — chat agent runtime async carve-out
**Choice:** The future `/chat` streaming route — and only that route — is `async def`. Everything else (handlers, services) stays sync per CLAUDE.md rule 1.
**Why:** OpenAI Agents SDK only streams from an async iterator (`Runner.run_streamed`). Bridging via threads + queues was considered and rejected as more code for no benefit.
**Alternatives considered:** Hand-rolled OpenAI Chat Completions streaming loop (lose SDK tool loop, future hosted tools); thread-bridge sync handler.

## 2026-05-09 — class-based Tool ABC over `@function_tool`
**Choice:** Tools subclass `Tool[TArgs, TResult]` and own their packet types + emit lifecycle. SDK integration via `FunctionTool(...)` adapter at `app/agents/runtime.py:_adapt`.
**Why:** Each tool needs to emit per-tool typed packets (`<tool>_start/_call/_end`). The decorator form makes packet ownership awkward and forces all tool result types through `dict`.
**Alternatives considered:** `@function_tool` with a side-channel registry of packet types; ToolSpec dataclass + decorator hybrid.

## 2026-05-09 — OpenRouter via Chat Completions, not Responses
**Choice:** `OpenAIChatCompletionsModel` against OpenRouter base URL.
**Why:** OpenRouter implements Chat Completions only; Responses API is OpenAI-direct.
**Alternatives considered:** Wait for OpenRouter Responses support — not viable on this timeline.

## 2026-05-09 — `manage_memory` action discriminator with model_validator
**Choice:** Single tool with `action: create|update|delete` and `model_validator(mode="after")` enforcing per-action required fields, rather than a Pydantic discriminated union.
**Why:** LLMs occasionally drop the discriminator key; flat schema with explicit validation is more forgiving.
**Alternatives considered:** Three separate tools; discriminated union per action.

## 2026-05-09 — manage_memory update cannot clear fields to NULL
**Choice:** None-from-LLM on `update` is treated as "omitted" (mapped to `_UNSET`), not "set to NULL". Implemented in `_unset_unprovided` at `app/agents/tools/memory.py`.
**Why:** The LLM cannot natively express the difference between "I'm not setting this" and "I'm clearing this". Clearing is rare in this app.
**Alternatives considered:** Add a `clear_fields: list[str]` arg — defer until a real need shows up.
