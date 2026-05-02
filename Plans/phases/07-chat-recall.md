# Phase 07 — Chat recall (intent classifier + search tools)

## Goal
Add a real intent classifier (capture vs recall) and the read-side tools so the agent can answer questions about the user's past with cited dates.

## Functional requirements
Agent updates:
- Intent classifier runs first on each user turn. Two intents for now: `capture`, `recall`. Ambiguous → defaults to `capture`. May ask **at most one** clarifying question.
- Recall flow: status event "Searching your memory…" → 1–N tool calls (≤ 5 total) → streamed prose answer ≤ 3 short paragraphs, citing memories with dates the UI can detect (e.g., explicit ISO dates).

New tools:
- `search_facts(query, date_range?)` — if no fact embeddings yet (phase 11 not shipped), fall back to keyword search over `facts.text` + `entries.text` using Postgres `tsvector`/GIN. Same signature persists post-phase-11.
- `search_entries(query, date_range?)` — `tsvector` keyword search over entries; later upgraded to vector search.
- `list_memories(filters?)` — returns memory cards (delegates to phase-05 service layer).
- `get_entries_around(date, window_days)` — temporal context window.

Behaviours:
- Recall responses cite dates inline; the agent does **not** fabricate citations.
- Tool budget: max 5 tool calls per turn.
- Citations format is documented (e.g., `[2025-04-12]`) so the mobile UI can detect and link them.
- Capture path from phase 06 unchanged.
- If both intents look plausible, choose `capture` (it's reversible).

Indexes / data:
- Add `tsvector` columns + GIN indexes on `entries.text` and (if not already) `facts.text` via a migration.

## Out of scope
- No reminders, image-attach, or meta yet.
- No semantic vector search yet (lit up in phase 11 by adding embedding-based ranking inside the same tool functions).
- No personalisation from `profiles` (phase 13).

## Depends on
- 03, 04, 06

## Verification
- pytest: capture-then-recall flow — create 5 memories, ask "what did I do yesterday", agent calls `search_entries`/`search_facts`, response cites at least one matching date.
- Recall-vs-capture classifier test set (≥ 20 hand-written examples) ≥ 90% correct.
- Tool budget enforced: a query that could call 8 tools stops at 5.
- First-token latency for recall < 1s p95 on a small dataset.

## Master-plan refs
- §4.2 (recall flow & acceptance), §7.2 (jobs), §7.3 (read tools), §10.1 (eval categories — used as a sanity gut-check, full eval lives at phase 11+).
