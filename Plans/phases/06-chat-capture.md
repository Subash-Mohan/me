# Phase 06 — Chat endpoint, streaming, capture-only agent

## Goal
A working chat endpoint that streams agent responses, persists the conversation/messages, and uses a single tool `save_memory` to turn every user turn into a memory. Intent classification is hard-coded to "capture" — that's all the agent can do in this phase.

## Functional requirements
Endpoints:
- `POST /conversations` — start a new conversation; returns conversation id.
- `GET /conversations` — list user's conversations (id, title, last_message_at).
- `POST /conversations/{id}/messages` — body: `{client_uuid, content, tz}`. Persists the user message synchronously (< 200ms p95) and returns immediately with the message row. **Does not** wait for the agent.
- `GET /conversations/{id}/stream?after=<message_id>` (SSE) — streams agent tokens, tool-call status events ("Saving…"), and the final assistant message id when done.
- Alternative single-shot: combine post + stream behind one endpoint if simpler — record choice in `DECISIONS.md`.

Agent behaviour:
- Receives the new user message + last N turns from the same conversation.
- Hard-coded intent = `capture`. Calls `save_memory(text, event_date?, mood?, tags?)` exactly once.
- Replies with a short acknowledgement ("saved.") plus, if it inferred mood/tags, one short line stating them.
- Tool call emits a status event over SSE before and after.

Tools (in `app/agents/tools/`):
- `save_memory(text, event_date?, mood?, tags?)` — creates an entry + memory in one transaction, linked to the originating message id. Honours "yesterday I…" by accepting a backdated `event_date`.

Behaviours:
- Idempotency: repeating a `POST /messages` with the same `client_uuid` returns the existing message — does not create a duplicate.
- Send path is synchronous DB write only; LLM call happens during the SSE stream.
- LLM provider via OpenRouter using OpenAI SDK; model id from user preference or `OPENROUTER_DEFAULT_MODEL`.
- LLM outage during streaming: stream a friendly error event, message + entry are already saved, capture still succeeds.
- Per-user daily LLM-call counter increments; soft cap → degrade to cheaper model (no hard fail).
- Conversation history sent to the model is the last N messages plus a placeholder for "rolling summary" (real summarisation is later — keep the seam).

## Out of scope
- No recall, no reminders, no image attach, no profile edits.
- No real intent classifier (always capture).
- No fact extraction (phase 11).
- No image-bearing capture (phase 09).

## Depends on
- 03, 04

## Verification
- `curl -N` to the SSE endpoint streams tokens, then a `tool: save_memory` event, then `done`.
- pytest: post a message, observe an entry + memory created, observe an assistant message persisted.
- Repeat the same `client_uuid` → still one message, one entry, one memory.
- Kill the LLM (point at unreachable URL) → user message and entry still persist; SSE emits an error event.
- Send time: message persisted and acked < 200ms p95 (without waiting for LLM).

## Master-plan refs
- §4.2 (chat surface behaviours and acceptance), §6.1 (sync/async), §6.3 (idempotency), §7.3 (capture tool).
