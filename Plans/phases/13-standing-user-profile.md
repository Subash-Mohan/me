# Phase 13 — Standing user profile + weekly regeneration

## Goal
Maintain a small (~300–500 token) text profile per user, regenerated weekly, prepended to extractor and chat-agent system prompts. Users can read, edit, and trigger regeneration manually.

> **Read `personal_memory_layer_guide.pdf` before implementing this phase** — it specifies the prompt used for profile generation.

## Functional requirements
Storage:
- `profiles` row already exists (phase 03). Stores `text` and `regenerated_at`.

Regeneration job:
- `pg_cron` job (or APScheduler equivalent) runs weekly at a per-user-configurable time (default Sunday 03:00 user-local).
- For each user: read last 30 days of entries + a sampled set of older active facts → LLM produces a 300–500 token profile → write to `profiles.text` with `regenerated_at = now()`.
- Manual trigger: `POST /profile/regenerate` enqueues a one-off run; same code path.
- Token-budget aware: trims input if user has many entries.

Integration:
- Capture/recall agents (phases 06–10) prepend `profiles.text` to the system prompt at request time.
- Fact-extraction worker (phase 11) prepends `profiles.text` to the extractor prompt.

Endpoints (carry-over from phase 10):
- `GET /profile`, `PATCH /profile`, `POST /profile/regenerate`.

## Out of scope
- Multi-profile / persona switching.
- Conversation summarisation (separate concern, can be folded in later).

## Depends on
- 11 (uses fact embeddings to sample older facts), 10 (endpoints already shipped).

## Verification
- pytest: seed 30 days of entries → run regen job → `profiles.text` is non-empty and ≤ 500 tokens.
- Regen scheduled at the user's configured time (use a frozen-time test).
- `POST /profile/regenerate` returns immediately; profile updates within seconds in dev.
- Verify the chat-agent system prompt at runtime includes the profile text (snapshot test of the assembled prompt).

## Master-plan refs
- §4.5 (profile), §7.3 (`update_profile` tool, `get_user_profile` read tool).
