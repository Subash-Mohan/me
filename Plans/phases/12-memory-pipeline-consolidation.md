# Phase 12 — Consolidation, bi-temporal facts, reprocess-all

## Goal
Make facts evolve correctly over time: ADD/UPDATE/DELETE/NOOP decisions when new facts arrive, bi-temporal columns honoured by all reads, and a one-shot admin command that re-extracts every entry from scratch.

> **Read `personal_memory_layer_guide.pdf` before implementing this phase.**

## Functional requirements
Consolidation step (added to the phase-11 pipeline, after fact extraction):
- For each newly extracted fact:
  1. Retrieve top-K similar existing facts for this user via vector search (already available from phase 11).
  2. LLM call decides one of: `ADD` (new), `UPDATE` (this supersedes an older fact), `DELETE` (this contradicts and invalidates an old fact), `NOOP` (duplicate / not informative).
  3. Apply:
     - `ADD`: insert.
     - `UPDATE`: insert new fact; mark older fact `invalid_at = now()` and `expired_at = now()`. Link both to source entries.
     - `DELETE`: mark older fact invalid; do not insert the new one (or insert as a "negation" depending on guide).
     - `NOOP`: drop.
- Every fact carries `valid_at` (when the fact became true), `invalid_at` (nullable — when superseded), `created_at` (row creation), `expired_at` (when invalidated).

Read-side updates:
- All recall tools filter `invalid_at IS NULL` by default.
- `get_timeline(entity)` (new tool) returns chronological facts about an entity — fits naturally here.
- Knowledge-update queries (master plan §10.1) work because invalidated facts coexist with their successors.

Memory edits / deletes (revisit phase 05):
- Deleting a memory (and thus its entry) marks all facts whose **only** source is that entry as invalidated; multi-source facts are kept but the source link is removed.
- Editing memory text flags the entry for re-extraction (`extraction_jobs` row with `version += 1`); the worker handles it via the same idempotency rule from phase 11.

Admin command:
- `app.workers.admin.reextract_all_entries(--dry-run, --user-id=)` — drains and re-runs the full pipeline over every entry. Output stable: re-running it twice produces the same fact set.

## Out of scope
- Eval set (master plan §10) is built **alongside** this phase but lives in `tests/eval/` — running it is gated on data, not on this phase shipping.
- LLM fine-tuning, RLHF, etc.

## Depends on
- 11

## Verification
- pytest: capture two contradictory statements ("I love coffee" → later "I quit coffee"). After both run, recall correctly says the user quit; the older fact has `invalid_at` set.
- pytest: post the same fact twice (two entries, same content) → second consolidation returns NOOP, fact count == 1.
- `reextract_all_entries --dry-run` counts the same number of facts as a fresh real run on a seeded DB.
- Delete a memory whose entry is the sole source of fact X → fact X becomes invalid.
- Eval set (≥ 30 questions, five categories per master plan §10.1) runs and reports per-category scores; phasing target ≥ 60% LLM-as-judge.

## Master-plan refs
- §4.4 (consolidation step), §6.2 (entries source of truth & reprocess command), §10.1 (eval categories).
