# Phase 05 — Memory list / detail / edit / delete endpoints

## Goal
Authenticated CRUD for the memory browser — list, view, edit, delete. No LLM in this path. No capture endpoint here (capture lives in chat, phase 06).

## Functional requirements
Endpoints (all under `current_user`):
- `GET /memories` — reverse-chronological list. Query params: `from`, `to` (date range on `event_date`), `tag`, `limit`, `cursor`. Returns memory cards (id, event_date, first ~3 lines of text, mood, tags, image thumbnails refs).
- `GET /memories/{id}` — full memory: text, all images, mood, tags, event_date, created_at.
- `PATCH /memories/{id}` — partial update of text, mood, tags, event_date. `created_at` is immutable.
- `DELETE /memories/{id}` — soft delete (set `deleted_at`); excluded from list/detail thereafter. Hard delete is reserved for account-wide purge (phase 10).
- `POST /memories/{id}/images` — list image_ids to attach (re-using already-uploaded images by id). Image upload itself is phase 09.
- `DELETE /memories/{id}/images/{image_id}` — detach an image from this memory; image blob is unaffected.
- `PATCH /memories/{id}/images` — reorder images.

Behaviours:
- All routes 404 if the memory doesn't belong to the caller.
- Edits update `entries.text` / `entries.event_date` / `entries.mood` / `entries.tags` (entries = source of truth) and the joined `memories` row.
- A memory edit marks any derived facts as stale (`extraction_status = 'needs_reextraction'`) — actual re-extraction is phase 12. For now: just flag.
- A memory delete cascades to memory_images join rows, leaves images and facts in place (facts get invalidated in phase 12).
- Filter bar in the UI uses `from`/`to`/`tag`; full-text and semantic search are intentionally **not** here — users go to chat for that.
- List endpoint p95 < 500ms for 1000 memories.

## Out of scope
- No image upload here (phase 09).
- No fact invalidation logic yet (phase 12).
- No semantic / keyword search endpoints (chat-only, phase 07+).

## Depends on
- 03, 04

## Verification
- pytest integration tests cover: list with date filter, list with tag filter, edit propagates to entry, delete hides from list, cross-user access is 404, reorder images.
- Manual: seed 1000 memories, hit `/memories?limit=50` — < 500ms.

## Master-plan refs
- §4.3 (memory browser behaviours & acceptance), §6.2 (source of truth = entries).
