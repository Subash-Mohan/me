# Phase 11 — Memory pipeline: background worker, embeddings, fact extraction

## Goal
Background worker processes new entries: generates entry embeddings, extracts atomic facts via LLM, persists facts. Recall (phase 07) starts using vector search transparently.

> **Read `personal_memory_layer_guide.pdf` before implementing this phase.**

## Functional requirements
Worker process:
- Same Docker image as the API; `worker` entrypoint (different command).
- Polls `extraction_jobs` (FOR UPDATE SKIP LOCKED) for `pending` rows or uses LISTEN/NOTIFY — record choice in `DECISIONS.md`.
- Concurrency configurable via env (`WORKER_CONCURRENCY`).

Pipeline per entry:
1. **Embedding** — generate `entry_embeddings` row (model id from `EMBEDDING_MODEL` env). Default: a small cheap model (`text-embedding-3-small` or equivalent).
2. **Fact extraction** — call the LLM with: standing profile (phase 13 placeholder OK), small context window of nearby entries, and the entry. Output schema: list of `{text, event_time, entities, category, confidence}`.
3. **Persist** — insert each fact + a `fact_sources(fact_id, entry_id)` link. Each fact gets its own embedding (`facts.embedding`).
4. Mark job `done`. On failure, increment `attempts`, record `last_error`, requeue with exponential backoff. After 5 attempts mark `extraction_failed` (surfaces in `/needs-attention`).

Triggering:
- Phase 06's capture path enqueues an `extraction_jobs` row immediately after the entry is committed.
- Re-running extraction on an entry must not duplicate facts: implement either (a) replace-by-entry semantics (delete previous facts derived solely from this entry, then insert) or (b) idempotency key per (entry_id, extraction_version).

Recall upgrade:
- `search_facts(query, ...)` and `search_entries(query, ...)` now use vector similarity (pgvector) **and** the existing tsvector — combine via simple rank fusion. No API surface change.
- `list_memories` unchanged.

Latency:
- p95 from "entry committed" → "facts queryable" < 60s on a quiet system.

Observability:
- Structured logs per job: entry id, latency per stage, fact count, model used. Never log the entry text.
- Counters: jobs in queue, jobs failed, average latency.

## Out of scope
- Consolidation (ADD/UPDATE/DELETE/NOOP) — phase 12.
- Bi-temporal logic on facts beyond the columns existing — phase 12.
- Image embeddings — V2.

## Depends on
- 03, 06, 07. Coexists with the rest.

## Verification
- pytest: post a capture → after worker tick, at least one fact + entry embedding exist; `search_facts("…")` returns the new fact.
- Force LLM failure → job reaches `extraction_failed` after 5 retries; the entry/memory are still browsable.
- Re-enqueue an already-extracted entry → fact count stays the same (no duplicates).
- 95th percentile end-to-end latency under 60s on a 100-entry seed.

## Master-plan refs
- §4.4 (memory pipeline), §6.5 (extraction unlimited / cost), §10.2 (60s lag p95), §13 (open questions on models/retries).
