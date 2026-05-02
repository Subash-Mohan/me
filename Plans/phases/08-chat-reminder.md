# Phase 08 — Reminder intent + scheduling + dispatch

## Goal
The agent can parse "remind me to …" requests, confirm with the user, and store reminders that fire on time. A scheduler dispatches due reminders via FCM (stubbed locally — real FCM in phase 15).

## Functional requirements
Agent:
- Intent classifier extended: `capture`, `recall`, `reminder`. Reminder triggers when the user clearly asks to schedule something.
- Reminder flow: parse → restate parsed time/recurrence in natural language → wait for "yes" → call `set_reminder`. No more than one clarifying turn.
- Tool: `set_reminder(message, when_iso_local, tz, recurrence?)` — `recurrence` ∈ `none|daily|weekly`. Returns the reminder id; agent confirms with "scheduled.".

Endpoints:
- `GET /reminders` — list user's upcoming + recurring reminders.
- `PATCH /reminders/{id}` — edit message / fire_at / recurrence / status.
- `DELETE /reminders/{id}` — cancel.
- `POST /reminders/{id}/snooze` — body `{minutes}` reschedules and re-arms.

Scheduler:
- A worker job runs every minute (`pg_cron` if extension enabled, otherwise APScheduler in-process — record choice in `DECISIONS.md`).
- Job picks up reminders where `next_fire_at <= now()` and `status = 'pending'`. For each:
  1. Mark `status = 'sending'` (row-level lock to prevent double-dispatch).
  2. Call the dispatch service (FCM stub: log payload).
  3. On success: set `status = 'sent'` for one-shots; reschedule `next_fire_at` for recurring.
  4. On failure: backoff and leave `pending`.
- Dispatch service interface is split (`Dispatcher` protocol) so phase 15 swaps the stub for real FCM without touching the scheduler.
- Timezone correctness: `fire_at_local` + `tz` is the source of truth; `next_fire_at` is computed in UTC and survives DST.

## Out of scope
- Real FCM credentials (phase 15).
- Browser/web push.
- Snoozing from the chat (use endpoint for now; chat snooze can come later).

## Depends on
- 03, 04, 06, 07

## Verification
- pytest: ask agent "remind me to call Mom at 6pm tomorrow" → agent restates → user confirms → reminder row exists with correct `fire_at_local` + `next_fire_at`.
- Manual: insert a reminder with `fire_at` 2 minutes in the future → within 60s of the scheduled time, the dispatcher logs the payload (FCM stub).
- Recurring weekly reminder fires once, then `next_fire_at` advances by 7 days correctly across a DST boundary (use a frozen-time test).
- Concurrent scheduler runs do not double-dispatch (row lock test).

## Master-plan refs
- §4.6 (reminders), §6.7 (time/TZ), §7.3 (set_reminder tool), §10.2 (60s firing accuracy).
