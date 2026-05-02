# Phase 10 — Meta intent, profile, settings, export, delete-account

## Goal
Round out the chat surface with the `meta` intent, expose a profile that the user can read/edit (regeneration is phase 13), and ship the settings-screen API: model selection, needs-attention list, full data export, and account deletion.

## Functional requirements
Agent:
- Intent classifier extended with `meta`: profile edits, model changes, settings-style commands.
- Tool: `update_profile(new_text)` — overwrites `profiles.text`; restates a brief diff back to the user.
- Tool: `set_model(openrouter_model_id)` — updates `users.model_preference` after validating the id is on an allow-list.

Endpoints:
- `GET /profile` / `PATCH /profile` — read/edit the standing profile.
- `POST /profile/regenerate` — triggers regeneration **on demand** (the actual job is phase 13; this just enqueues).
- `GET /settings` — returns: model preference, notification preferences, daily LLM budget + usage, timezone.
- `PATCH /settings` — updates the writable subset (model preference, notifications, timezone).
- `GET /needs-attention` — entries with `extraction_failed` (real entries appear after phase 11).
- `GET /export` — streaming JSON download of: user, conversations, messages, entries, memories, facts, reminders, profile, image refs (NOT blobs — but include signed URLs at request time).
- `DELETE /account` — body `{confirm: "DELETE"}`. Soft-marks the account for deletion; a worker job hard-deletes within 24h (rows + image blobs). Token is invalidated immediately.

Behaviours:
- Model preference validated against an allow-list configured via env (`OPENROUTER_ALLOWED_MODELS`), default contains a couple of cheap and capable options.
- Export endpoint streams chunks (large users); never loads the whole dataset in memory.
- Delete-account is irreversible after the 24h grace; the response makes that clear.
- LLM budget surfaced in `/settings` reflects the same counter capture/recall already increment.

## Out of scope
- Weekly review chat surface (V2, later phase).
- "On this day" (V2, later phase).
- Multi-device session listing.

## Depends on
- 03, 04, 05, 06, 07, 09

## Verification
- pytest: agent "change my model to anthropic/claude-3.5-haiku" → `users.model_preference` updated.
- `GET /export` round-trips a small fixture user; output validates against a JSON schema you write here (a few fields is enough).
- `DELETE /account` with the right confirmation marks the row; running the purge worker once removes all related rows + blobs.
- `GET /needs-attention` returns 200 with an empty list pre-phase-11.

## Master-plan refs
- §4.5 (profile), §4.9 (settings), §7.3 (update_profile tool), §6.4 (privacy / data export & delete).
