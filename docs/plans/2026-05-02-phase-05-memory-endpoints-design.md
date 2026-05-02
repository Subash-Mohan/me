# Phase 05 — Memory endpoints (design)

**Date:** 2026-05-02
**Phase file:** `Plans/phases/05-memory-endpoints.md`
**Status:** approved, ready for implementation plan

This design refines the phase-05 spec after a brainstorm. Anything below
that contradicts the phase file is the intended deviation; deviations are
mirrored in `DECISIONS.md` so phase 06+ readers see them.

---

## Goal

Authenticated CRUD for the memory browser: list, view, edit, soft-delete.
Sync handlers, no LLM, no worker, no images. Phase 05 introduces the
`memories` table and is the first phase to actually populate the data layer
beyond `users`.

---

## Data model

### One new table

```
memories
  id          BIGINT IDENTITY PK
  user_id     UUID NOT NULL FK → users(id) ON DELETE CASCADE
  message_id  UUID NULL                                -- FK added by phase 06's migration
  text        TEXT NOT NULL
  event_date  DATE NOT NULL
  event_tz    TEXT NOT NULL DEFAULT 'UTC'              -- IANA tz at capture time
  mood        TEXT NULL                                -- no CHECK; phase 06 adds vocab
  tags        TEXT[] NOT NULL DEFAULT '{}'
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
  deleted_at  TIMESTAMPTZ NULL                         -- soft-delete sentinel

indexes
  (user_id, event_date DESC, id DESC) WHERE deleted_at IS NULL    -- list + cursor
  GIN(tags)                            WHERE deleted_at IS NULL    -- tag filter
  UNIQUE(user_id, message_id)          WHERE message_id IS NOT NULL  -- one memory per chat message
```

Per phase 03 conventions: hand-written migration (partial indexes + GIN +
UNIQUE WHERE clauses don't autogenerate cleanly).

### What's deliberately NOT in this phase

- `entries` table — removed during brainstorm. `memories` is now the
  source of truth (see DECISIONS supersede). Re-extraction in phase 12
  re-derives facts from memories, not from a separate entries table.
- `images`, `memory_images` — deferred to phase 09 along with all
  image-related endpoints. Phase 05 ships nothing image-shaped.
- `extraction_status` flag — dropped. Phase 12 polls `memories.updated_at`
  to find what's gone stale since its last extraction run.
- CHECK constraint on `mood` — phase 06 owns the vocab (it's the LLM
  extraction prompt that decides the values) and will add the CHECK then.

### `message_id` and the FK to `messages`

`messages` doesn't exist until phase 06. `message_id` ships as a UUID
column without a FK constraint in phase 05; phase 06's migration adds
the FK in the same revision that creates `messages`. The UNIQUE partial
index on `(user_id, message_id) WHERE message_id IS NOT NULL` is enforced
from phase 05 — it's index-side enforcement that needs no FK.

The column is nullable so test fixtures can seed memories without
fabricating message rows.

---

## Endpoints

All routed under `Depends(current_user)` from phase 04. All return JSON.

| Method | Path | Body / Query | Extra auth | Success |
|---|---|---|---|---|
| GET | `/memories` | `from`, `to`, `tag`, `limit`, `cursor` (query) | — | 200 + page |
| GET | `/memories/{id}` | — | — | 200 + detail |
| PATCH | `/memories/{id}` | `MemoryPatch` | — | 200 + updated detail |
| DELETE | `/memories/{id}` | — | `X-Confirm-Passphrase` (`Depends(confirm_passphrase)`) | 204 |

### List — `GET /memories`

Query params:
- `from`, `to` — `event_date` range, inclusive both ends. Either may be omitted.
- `tag` — single string. Matches via `tags && ARRAY[$1]` (any-of).
- `limit` — default 50, cap 200.
- `cursor` — opaque base64 token (see below).

Response:
```json
{
  "items": [ { "id": 12345, "event_date": "2026-04-12",
               "text_preview": "...", "mood": "content",
               "tags": ["work","focus"] }, ... ],
  "next_cursor": "eyJlZCI6IjIwMjYtMDQtMTIiLCJpZCI6MTIzNDV9" | null,
  "has_more": true | false
}
```

`text_preview` is computed server-side: first ~200 chars OR first 3 lines,
whichever is shorter. Pure function, no second column. The full text is
fetched via the detail endpoint.

Sort key is fixed: `(event_date DESC, id DESC)` — no client control. The
covering partial index handles list+filter+pagination in one scan.

### Detail — `GET /memories/{id}`

```json
{ "id": 12345,
  "event_date": "2026-04-12",
  "event_tz": "Asia/Tokyo",
  "text": "full memory text here",
  "mood": "content",
  "tags": ["work","focus"],
  "created_at": "2026-04-12T01:23:45Z",
  "updated_at": "2026-04-12T01:23:45Z" }
```

Returns 404 if the row doesn't exist, belongs to a different user, or has
`deleted_at IS NOT NULL`. Cross-user is folded into 404 to avoid leaking
existence (moot today with one user, principle stays).

### PATCH — `PATCH /memories/{id}`

Request body, every field optional:
```json
{ "text":       "...",                // present → replace
  "event_date": "2026-04-12",         // present → replace
  "tz":         "Asia/Tokyo",         // required iff event_date present
  "mood":       null | "content",     // present → set/clear
  "tags":       ["a","b"] }           // present → replace whole array
```

Per-field rules:
- `text` — non-empty when present, whitespace-trimmed.
- `mood` — explicit `null` clears, missing leaves alone, string sets.
- `tags` — replace-whole-array. `[]` clears. Server lower-cases,
  whitespace-trims, and de-dupes.
- `event_date` — present → replace. Cannot be `null`. **When present,
  request must also carry `tz` (IANA name)** — server overwrites
  `event_tz` with that value, on the rule that the new date was stated
  in the user's current TZ.
- `created_at`, `id`, `user_id`, `message_id` — never patchable;
  ignored if present (or 422 if pydantic strict-mode).

Response: full updated detail body (same shape as `GET /memories/{id}`).

Validation outcomes:
- 422 — empty body, empty text, `event_date` present without `tz`.
- 404 — row missing / soft-deleted / not owned.

PATCH does not require step-up auth: edits are reversible (re-edit). No
ETag / optimistic locking — last-write-wins, single user, single device.

### DELETE — `DELETE /memories/{id}`

- Requires `X-Confirm-Passphrase` header verified by
  `Depends(confirm_passphrase)` (the dep already shipped in phase 04
  exactly for this surface).
- Soft-delete: `UPDATE memories SET deleted_at = now() WHERE id = $1
  AND user_id = $2 AND deleted_at IS NULL`.
- 204 on hit (whether the row was already deleted or freshly deleted —
  idempotent on success).
- 404 only when the row doesn't exist for this user at all.
- 401 if `X-Confirm-Passphrase` is missing or wrong (handled by the dep).

Hard delete is reserved for the account-wide purge (phase 10).

---

## Cursor encoding

Opaque base64 of a tiny JSON object:
```
{"ed": "YYYY-MM-DD", "id": <int>}
```

Server emits `next_cursor` for the row immediately *after* the last item
on the returned page. Client sends it back verbatim as `?cursor=...`.

WHERE clause for `?cursor=...`:
```sql
WHERE (event_date, id) < (cursor.ed, cursor.id)
```
(Tuple comparison gives the right "strictly older" semantics under the
sort `(event_date DESC, id DESC)`.)

The encoding is internal — clients don't construct it. Keeps us free to
add a tiebreaker, switch to a signed token, or change the sort without a
client contract change. Helper lives in `app/services/memories.py` (or
its own module if it grows past ~30 lines).

---

## Code layout

```
app/api/memories.py                — router; one function per endpoint
app/services/memories.py           — list/detail/patch/delete + cursor codec
app/models/memory.py               — Memory ORM + re-export from app/models/__init__.py
app/schemas/memory.py              — Pydantic:
                                       MemoryCard, MemoryDetail,
                                       MemoryPatch, MemoryListResponse,
                                       Cursor (internal)
migrations/versions/<rev>_memories.py  — hand-written
tests/_db.py                       — extend reset_db() to TRUNCATE memories
                                     (CASCADE from users handles FK chain),
                                     add seed_memory(...)
tests/api/test_memories_list.py
tests/api/test_memories_detail.py
tests/api/test_memories_patch.py
tests/api/test_memories_delete.py
tests/unit/test_memory_cursor.py
```

Each `tests/api/test_memories_*.py` declares `_setup` (autouse,
module-scoped) that resets + seeds the owner, matching the phase-04
test convention. Tests within a module run in source order and may share
state.

`app/main.py` registers the new router:
```python
from app.api.memories import router as memories_router
app.include_router(memories_router)
```

---

## Observability

Structured log events (no payload bodies; ids, counts, types only):
- `memory.list_ok` — `{user_id, count, has_filters, has_cursor}`
- `memory.detail_404` — `{user_id, memory_id}`
- `memory.patch_ok` — `{user_id, memory_id, fields_changed: ["text","tags"]}`
- `memory.delete_ok` — `{user_id, memory_id}`
- `memory.delete_step_up_fail` — `{user_id, memory_id, ip}`

CLAUDE.md privacy rule §5 applies: never log `text`, `tags`, `mood`,
or any passphrase / token.

---

## Cross-cutting rules satisfied

- §1 (revised) — `memories` is source of truth; nothing here mutates
  derived state. (See DECISIONS supersede entry.)
- §2 — sync handlers, no `await`, no LLM. No worker dependency.
- §3 — DELETE is idempotent on hit. PATCH is field-level idempotent.
- §5 — only ids/counts/types logged.
- §7 (runtime) — every endpoint works without LLM, image storage, worker,
  or extraction pipeline. Phase 11/12 outages cannot affect this surface.

---

## Verification (refines phase-file's verification list)

pytest integration tests (real Postgres, per-module reset):
- list — empty result; date filter; tag filter; combined filters; pagination
  cursor round-trip across two pages; sort by `(event_date DESC, id DESC)`
  including event_date ties broken by id.
- detail — 200 happy path; 404 on missing; 404 on soft-deleted; 404 on
  cross-user (will be exercised once a second user can be seeded; for now
  asserted via direct fixture).
- PATCH — text replace; tags replace + clear via `[]`; mood set + clear
  via explicit `null`; event_date with tz overwrites event_tz;
  422 on empty body; 422 on event_date without tz; 404 on
  missing/soft-deleted; created_at unchanged; updated_at bumped.
- DELETE — 204 on first delete; 204 on re-delete (idempotent); 404 on
  missing id; 401 on missing `X-Confirm-Passphrase`; 401 on wrong
  passphrase; soft-deleted row disappears from list/detail.
- cursor codec unit tests — encode then decode round-trips; rejects
  malformed input with a typed error.

Manual perf check (deferred, optional): seed 1000 memories, hit
`/memories?limit=50` — assert p95 < 500ms. The covering partial index
makes this comfortable; we don't need a load-test harness yet.

---

## DECISIONS.md entries this phase will append

1. **Phase-05 spec deviation: image endpoints + tables deferred to phase
   09.** Phase 05 ships only `memories`; `images`, `memory_images`, and
   the `POST/DELETE/PATCH /memories/{id}/images` endpoints all move to
   phase 09 where they can be E2E-tested with real upload.
2. **Source-of-truth supersede.** Replaces CLAUDE.md cross-cutting rule
   §1: `memories` is the source of truth (was: `entries`). Pipeline is
   `messages → memories → facts`. Re-extraction = re-derive facts /
   embeddings from memories. The `entries` table is removed from the
   plan. Phase 11/12 specs that mention "re-extract from entries" should
   be read as "re-extract from memories".
3. **`mood` vocabulary deferred to phase 06.** Phase 05 ships
   `mood TEXT NULL` with no CHECK constraint. Phase 06's extraction
   prompt picks the vocab; phase 06's migration adds the CHECK.
4. **Cursor encoding: opaque base64 of `{"ed":"YYYY-MM-DD","id":<int>}`.**
   Internal format; clients treat as opaque. Frees us to evolve sort /
   tiebreakers / signing without a client change.
5. **Concurrency: last-write-wins on PATCH; no ETags / If-Match.**
   Single-user, single-device deployment makes optimistic locking
   ceremony with no payoff.
6. **`memories.message_id` ships without FK in phase 05.** The FK to
   `messages(id)` is added by phase 06's migration in the same revision
   that creates `messages`. The UNIQUE partial index on
   `(user_id, message_id) WHERE message_id IS NOT NULL` is enforced
   from phase 05.
7. **`extraction_status` flag dropped from phase 05.** Phase 12 will
   poll `memories.updated_at` to find rows whose facts have gone stale
   since the last extraction run. Saves shipping a column whose only
   consumer doesn't exist yet.

---

## Out of scope (reaffirmed from spec)

- No image upload, image attach, or image reorder (phase 09).
- No fact invalidation / re-extraction (phase 12).
- No semantic / keyword search endpoints (chat-only, phase 07+).
- No `POST /memories` — capture lives in chat (phase 06).
- No multi-tag filter, no full-text filter, no sort control.
- No backward pagination.
