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

## 2026-05-11 — chat session/message persistence shape
**Choice:** Two tables — `sessions` and `messages`. Roles are `user` and `assistant` only; tool activity rides on the assistant row as a single `tool_activity JSONB` column. Assistant rows link to their triggering user row via `parent_message_id` (partial UNIQUE).
**Why:** A separate `tool_call` / `tool_result` row schema would double the row count per turn for journaling-style traffic and force every read of a session to JOIN tool rows. The UI only needs to display "what the user typed" + "what the assistant said"; tool activity is supporting context, not a first-class entity. `parent_message_id` keeps the door open to multiple regenerated assistant replies later (drop the partial UNIQUE on `WHERE … deleted_at IS NULL` and you immediately get a 1:N history).
**Alternatives considered:** OpenAI-style four-role schema (`user`/`assistant`/`tool_call`/`tool_result`); embedding tool activity inside a JSONB column on the user row (less clean — assistant text was no longer first-class).

## 2026-05-11 — client UUID is the user-message PK with full replay
**Choice:** `POST /chat` requires `client_message_id: UUID`. The user-message row's PK is that UUID. On dup with an existing assistant row, the endpoint replays the cached text as a single `TextDeltaPacket` + `RunDonePacket` over SSE and does not invoke the agent. On dup without one (prior failure), the agent runs again.
**Why:** CLAUDE.md cross-cutting rule 2 requires "Client supplies a UUID per chat message; backend upserts on it." Full-replay is the most useful interpretation — it lets a flaky-network client retry without double-charging the agent or double-running tool side effects. The `ManageMemoryTool`'s existing `idempotency_id` covers double-create on the no-cache retry path.
**Alternatives considered:** Short-window-only dedupe (simpler, but no replay guarantee); pending-state lock + 409 on retry (needs a stale-runs sweeper, doesn't match the user's "fail loud, manual retry" preference).

## 2026-05-11 — in-session-only history; cross-session = cold agent
**Choice:** The chat endpoint loads the last `chat_history_turns=10` user+assistant pairs from the *current* session and prepends them to the agent input. The agent has no awareness of other sessions. Instructions now read "current conversation only" instead of "no memory across turns."
**Why:** Matches the journaling product framing — memories are the long-term truth (via `search_memories`), and a chat session is one bounded conversation. Cross-session context-window growth would be unbounded and would mix unrelated threads. Within a session the user gets natural multi-turn dialogue.
**Alternatives considered:** Token-budgeted history (deferred — needs a tokenizer wiring); entire-session history (unbounded); no history at all (forces every clarification to re-search memories).

## 2026-05-11 — no durable mid-stream recovery for chat runs
**Choice:** If `run_agent_stream` emits an `ErrorPacket` or raises, the endpoint surfaces the error packet and does not write an assistant row. The user message row stays. Retry is the client's job (sending the same `client_message_id` re-runs the agent).
**Why:** The user explicitly chose "fail loud, manual retry" over either pending-state tracking or delta-streaming-to-DB. Both alternatives carry persistent in-flight state that needs sweeping when the server crashes.
**Alternatives considered:** Persist deltas as they stream + resume after disconnect (needs run-resumption from the Agents SDK, which doesn't advertise it); mark the user_message as `status=running` and 409 on retry until resolved (adds a stale-runs sweeper / TTL).


## 2026-05-16 — assistant turn persists as a step-keyed `events` timeline
**Choice:** Replace `messages.tool_activity` (a `{"calls":[…]}` JSONB blob) with `messages.events` — an ordered list of `TextEvent` and `ToolEvent` records, each carrying a 1-based monotonic `step` and a coarse `kind: "text"|"tool"`. Wire packets for text deltas and tool lifecycle packets carry the same `kind` and `step`; envelope packets (`start`/`finish`/`error`) do not. Step assignment is server-side (chat layer's `StepAssigner`), not tool-side — tools stay step-agnostic. `messages.content` stays as a separate text column, derived at write time from text events (single source of truth: events drive content).
**Why:** (a) Preserves text↔tool interleaving in the turn timeline — today's joined `content` + sibling `tool_activity` lost it. (b) Numeric `step` makes "this packet belongs to step N" trivial for the client reducer without parsing array indices. (c) Live SSE stream and history replay share one packet shape, so the FE uses **one** reducer for both. (d) `kind` lets the FE branch text/tool without parsing the granular `type` literal (e.g., `search_memories_start`).
**Alternatives considered:** Step only on tool calls (rejected — leaves text interleaving lost); event-sourced with `content` as a Postgres `GENERATED ALWAYS AS … STORED` column (deferred — Python-side derivation is simpler and the duplication is one-way: events → content); keep `tool_activity` and add a separate `step` column on each (rejected — array position vs explicit step in two places is a drift trap).

## 2026-05-16 — `replay_stream` rehydrates the full packet timeline
**Choice:** A retry of a cached turn no longer emits just `start` + one `text_delta` + `finish`. It walks `messages.events` in step order and re-emits the matching `text_delta` (one per text run, full content) and the three tool packets (`_start` / `_call` / `_end`) for each tool event, all carrying the persisted `step` and `kind`. Same packet types as the live stream → same client parser.
**Why:** A user retrying a turn that had a tool call now sees the same tool badges/results they saw originally. Per-character typing animation is intentionally lost on replay (one delta carrying the full text) — replay is recovery, not re-performance. Supersedes the 2026-05-16 wire entry below on a single point: `finish` is no longer the only post-text packet on the replay path.
**Alternatives considered:** Replay only emits text and a synthetic "tool was here" marker (rejected — drops too much info); replay rebroadcasts the original packet sequence char-by-char (rejected — we don't persist deltas, only step-joined runs; no useful benefit either).

## 2026-05-16 — chat stream framed by `start` / `finish`; `run_done` dropped
**Choice:** The chat SSE stream now opens with `StartPacket(assistant_message_id, session_id)` and (on a clean run) closes with `FinishPacket(reason, assistant_message_id)`. The id is allocated up front in `stream_turn` and passed explicitly to `record_assistant_message` so the value advertised on the wire equals the row's PK in Postgres. `RunDonePacket` is removed; the agent runtime no longer emits a terminal packet at all — end-of-stream is the generator exhausting, and framing belongs to the chat layer.
**Why:** Matches the Anthropic/Vercel framing every modern client expects. Up-front id eliminates the round-trip a client would otherwise need to stitch streamed text → eventual DB row. Single-user app with no shipped clients, so the wire break is free now and expensive to retrofit once anything depends on the current shape. Supersedes the 2026-05-11 "in-session-only history" framing only on the wire — the in-session-only history rule itself still stands.
**Alternatives considered:** Additive `start` + new `finish` alongside a deprecated `run_done` (rejected — no clients to migrate); pre-allocating the id in the route and threading it through `ChatTurn` (rejected — id is a stream concern, not a request concern).

## 2026-05-16 — chat SSE framed by `sse-starlette` `EventSourceResponse`
**Choice:** Replace the hand-rolled `StreamingResponse(media_type="text/event-stream")` with `sse_starlette.EventSourceResponse`. Generators in `_chat_stream.py` yield `{"event": <packet.type>, "data": <packet.model_dump_json()>}` dicts; sse-starlette frames them on the wire and provides 15s keep-alive pings, `X-Accel-Buffering: no`, and client-disconnect detection out of the box.
**Why:** The hand-rolled form had none of those guarantees and would silently fail behind proxies that buffer SSE. Cheaper to delegate framing than to re-implement pings/disconnect.
**Alternatives considered:** Stay on `StreamingResponse` and add the pings/headers manually (rejected — re-implementing a stable library).

## 2026-05-16 — `GET /sessions/{id}/messages` is newest-first by default
**Choice:** Move messages out of `GET /sessions/{id}` (which now returns metadata only) into a dedicated `GET /sessions/{id}/messages?before=<cursor>&limit=50`. `list_session_messages` gained a `direction: Literal["asc","desc"]="desc"` parameter; the route always passes `"desc"`. The cursor encodes `(created_at, id)` regardless of direction and the comparison flips accordingly.
**Why:** A chat UI wants "render the most recent N first, then scroll up to load older" — the previous ascending order forced the client to fetch the entire history (or guess) to find the tail. The detail route bundling messages forced clients to choose between re-paying the session payload on every scrollback or splitting the call anyway.
**Alternatives considered:** Keep messages embedded in `GET /sessions/{id}` and add a sibling messages endpoint (rejected — two paths returning overlapping data); have the client request `?direction=asc` for chat (rejected — sane default eliminates a footgun).

## 2026-05-14 — mobile client lives in `mobile/` as a pnpm workspace
**Choice:** Add a React Native client at `mobile/` as a sibling of `app/`. Repo root becomes a pnpm workspace (`package.json` + `pnpm-workspace.yaml` with `nodeLinker: hoisted`, plus `.npmrc` fallback) declaring only `mobile`. Python tree is untouched — `app/`, `migrations/`, `tests/`, `pyproject.toml` stay where they are. Stack: Expo SDK 54 + Expo Router v6 + React Native 0.81 + NativeWind v4 with **Tailwind pinned to `^3.4.17`** (NativeWind v4 is incompatible with Tailwind v4; v5 preview is not yet stable).
**Why:** A monorepo lets backend and client evolve together without separate repos. `mobile/` at root (not `apps/mobile/`) avoids moving the Python tree and rewriting alembic.ini / Makefile / Dockerfile paths. `nodeLinker: hoisted` is required for RN/Expo native module resolution under pnpm. NativeWind dominates RN styling weekly downloads (~6× Tamagui, ~7× Unistyles) and matches the Tailwind muscle memory the author already has; Tamagui's pre-built components are overkill for a two-screen app and Unistyles is lower-level styled-system.
**Alternatives considered:** Full `apps/backend + apps/mobile` restructure (rejected — gratuitous churn for a single client); standalone `mobile/` with no workspace (rejected — would block any future shared TS package without a reorg); Tamagui / Unistyles styling (rejected per above); Turborepo / Nx on top of pnpm (rejected — one JS package doesn't need orchestration).

## 2026-05-17 — chat screen animated background uses Reanimated, not Skia
**Choice:** Ambient "shooting-star" streak field on `/chat` is implemented with `react-native-reanimated` (already at `~4.1.1`) — one `useFrameCallback` clock driving 15 `Animated.View` streaks rendered via `expo-linear-gradient`. New component at `mobile/components/chat/asteroid-field.tsx`. Streak seeds are produced by a deterministic mulberry32 PRNG so layout is stable across re-renders. Lifecycle is gated by `AppState` (pause on background) and `useReducedMotion()` (don't mount at all when the OS asks for reduced motion).
**Why:** `@shopify/react-native-skia` + `<Atlas>` is the textbook-best primitive for many independently-animated particles, but it adds a ~10MB native binary and a new build surface for what is decoration at N=15. Reanimated is already in the dep tree, matches the existing animation stack (Moti wraps it), and a single shared progress clock keeps the per-frame work to a constant 15 `useAnimatedStyle` worklets. Skia is worth re-evaluating only if particle count grows past ~50 or the look needs trails / blending modes a `<View>` + `LinearGradient` can't express.
**Alternatives considered:** Skia + `<Atlas>` / `useRSXformBuffer` (rejected — disproportionate native dep weight at N=15); per-streak `withRepeat(withTiming, -1)` (rejected — spawns 15 independent animation drivers, no central pause point); Moti loops (rejected — declarative timeline API is awkward for continuous procedural motion with random per-particle seeds); Lottie pre-baked animation (rejected — fixed timeline can't give N streaks independent random speeds without N AE layers).

## 2026-05-17 — asteroid silhouettes via `react-native-svg`, not LinearGradient streaks
**Choice:** Each asteroid is an `Animated.View` wrapping an `<Svg>` + `<Path>` from `react-native-svg` (already at `^15.12.1`). Four hand-authored irregular polygon silhouettes are picked from at seed time so the field shows visual variety rather than 15 copies of the same blob. Each asteroid also tumbles on its own axis at a slow random rate (±0.6 rad/s), independent of the motion direction — rocks tumble; only directional streaks would point along motion. Supersedes the LinearGradient streak rendering choice from the prior entry on the visual primitive only — the Reanimated-over-Skia architecture and the lifecycle gating (`AppState` pause, `useReducedMotion` skip) are unchanged.
**Why:** First pass rendered streaks via `expo-linear-gradient` (transparent → particle color → transparent inside a thin rotated View). Read on-device as faint moving rectangles, not space ambience. SVG path silhouettes were always the second option from the design brainstorm; switching the inner render only is a tight blast radius (one component, no architectural rework) and uses a library already in the tree.
**Alternatives considered:** Keep streaks but soften with a glow / drop-shadow (rejected — `react-native`'s shadow on Android is unreliable and would need extra wrapper elements); raster PNG asteroid sprites (rejected — needs asset pipeline + multiple resolutions, no benefit over inline SVG at this size); revisit Skia for path drawing (rejected — see prior entry, still no need at N=15).

## 2026-05-17 — asteroid visual is now falling stars (comet head + fading tail), not rock silhouettes
**Choice:** Each item is a meteor / shooting-star comet: a small bright head with a fading tail behind it, aligned with the motion direction. The SVG combines a `<RadialGradient>`-filled `<Circle>` for the glowing head (center opaque → edge transparent, 3-stop falloff so the head reads as a soft glow rather than a hard disk) and a `<LinearGradient>`-filled rounded `<Rect>` for the tail (transparent → opaque toward the head). Rotation now matches the motion direction (no axis tumble — tumbling looks wrong on directional comets). Count dropped to 10, opacity raised to 0.5–0.9, speed range raised to 45–95 px/s — falling stars want fewer-but-brighter rather than many-and-faint. Supersedes the prior entry's visual on this point; the Reanimated architecture, `AppState` pause, `useReducedMotion` skip, and motion math are unchanged.
**Why:** Both prior visuals — symmetric LinearGradient streaks and irregular polygon rocks — read wrong on device. Streaks looked like blurry tic marks (symmetric fade gave no leading "spark"); polygon rocks read as small static shapes since they were too small for the silhouette to be legible. A comet shape (asymmetric tail + bright head) is the visual canonically associated with a "falling star" and gives the eye a direction of motion at a glance. Per-star gradient defs (`tail-${id}` / `head-${id}`) instead of a shared defs block because each comet has its own dimensions and reusing one set would force every star to the same size.
**Alternatives considered:** Animate the head's `r` to twinkle (rejected — `Path`/`Circle` attributes don't go through Reanimated's UI-thread style updates cleanly; would need `createAnimatedComponent` per element for marginal payoff); add a periodic streak across the screen for variety (rejected — the user picked a steady ambient field, not punctuated events); pre-render the comet to a PNG and use `Animated.Image` (rejected — multiple density buckets, no real perf gain at 10 instances).

## 2026-05-17 — chat agent prompt gained a narrow "verify before acting" rule
**Choice:** Add a `# Verify before acting` section to `CHAT_SYSTEM_PROMPT_TEMPLATE` in `app/agents/instructions.py`, between "When to use which tool" and "Time context". The rule is scoped per-tool: ask before `manage_memory` create when WHAT/WHEN/WHERE/WHO is unclear (don't invent fields); refuse `manage_memory` update without a `memory_id` from a search hit seen this turn; ask before `search_memories` only when the recall query is too vague to form ("tell me stuff"). Includes an explicit "don't ask on clear statements — 'I had pizza for lunch' is fine to save as-is" carve-out.
**Why:** The agent was inventing event_times, attributing events to whoever was last mentioned, and picking ambiguous memories to update. A blanket "ask before every tool" rule was considered and rejected — it would quiz the user on clear journaling entries, which is the opposite of the chat-first UX. The narrow framing only kicks in where guessing would persist a wrong fact or overwrite the wrong row.
**Alternatives considered:** Blanket "ask before any tool call" rule (rejected — UX regression on clear entries); putting the rule in tool descriptions in `app/agents/tools/memory.py` (rejected — cross-tool behavioural rules belong in the system prompt); a `clarify_with_user` tool (rejected — extra hop for what is naturally a plain assistant message).

## 2026-05-17 — auth throttling is DB-backed and trusted proxy headers are opt-in
**Choice:** Add an `auth_throttles` table and a small `app/services/auth_throttle.py` service to rate-limit `/auth/login` and `/auth/verify-passphrase` by `(action, client_ip)`. Change `client_ip()` so `X-Forwarded-For` is ignored unless `TRUST_PROXY_HEADERS=true`.
**Why:** The app has one real credential, so online guessing is the highest-value attack. DB-backed throttle state survives process restarts and works consistently across multiple app workers. Forwarded headers are attacker-controlled unless the deployment explicitly guarantees a trusted reverse proxy in front of the app.
**Alternatives considered:** In-memory counters (rejected — reset on restart and fragment across workers); always trusting `X-Forwarded-For` (rejected — easy to spoof); per-user throttling only (rejected — `/auth/login` must behave safely even before user existence is proven).

## 2026-05-24 — deploy artefacts live under top-level `deploy/`; edge is Caddy on host
**Choice:** New top-level `deploy/` directory holds the prod `Dockerfile`, `docker-compose.prod.yml`, `Caddyfile`, `env.example`, and a `README.md` operator runbook. The VPS topology is Caddy on the host (apt + its own systemd unit) reverse-proxying to a single Docker container running `uvicorn` bound to `127.0.0.1:8000`. The compose `env_file` reads `${ME_ENV_FILE:-/etc/me/env}` so local smoke tests can point at a non-system path without editing the file.
**Why:** Keeps prod artefacts visibly separated from the dev-only `docker/` compose (which only runs Postgres). Caddy on the host gives automatic Let's Encrypt cert management with one Caddyfile and no certbot wiring; running it on the host (not in a sibling container) avoids privileged-port binding inside Docker and cert-volume persistence concerns. A single-process API needs no supervisord/Procfile — Docker's `restart: unless-stopped` supervises the container, and the host's systemd supervises Docker and Caddy.
**Alternatives considered:** Caddy as a sibling container in compose (rejected — cert volume + `:80`/`:443` binding add complexity for no benefit at single-host scale); nginx + certbot (rejected — Caddy gives the same outcome in ~7 lines vs ~35 with no separate renewal tooling); Cloudflare Tunnel (rejected for now — adds a hard dependency on Cloudflare for the public endpoint); putting prod files inside the existing `docker/` directory (rejected — visually conflates dev DB compose with prod app compose).

