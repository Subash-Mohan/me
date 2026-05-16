/**
 * Server-shape TypeScript mirrors of the backend Pydantic models.
 *
 * Keep this file pure: no React, no I/O, no helpers. Just types that match
 * what the backend serializes on the wire.
 *
 * Source of truth — these mirror:
 *   - `app/schemas/sessions.py` (SessionRead, MessageRead, TextEvent, ToolEvent)
 *   - `app/agents/packets.py` + `app/agents/tools/memory.py` (packet payloads)
 */

// ─── Session / message resources ──────────────────────────────────────────

export type Role = "user" | "assistant";

export type TextEvent = {
  step: number;
  kind: "text";
  content: string;
};

export type ToolEventStatus = "ok" | "error";

export type ToolEvent = {
  step: number;
  kind: "tool";
  tool_call_id: string;
  tool: string;
  arguments: Record<string, unknown> | null;
  status: ToolEventStatus | null;
  result: Record<string, unknown> | null;
  error: string | null;
};

export type ServerEvent = TextEvent | ToolEvent;

export type ServerMessage = {
  id: string;
  role: Role;
  content: string;
  events: ServerEvent[] | null;
  parent_message_id: string | null;
  client_tz: string | null;
  created_at: string; // ISO 8601
};

export type MessagesPage = {
  items: ServerMessage[];
  next_cursor: string | null;
};

export type SessionRead = {
  id: string;
  title: string | null;
  created_at: string;
  last_message_at: string | null;
};

export type SessionListResponse = {
  items: SessionRead[];
  next_cursor: string | null;
};

// ─── SSE packet payloads (the `data:` JSON for each `event:` line) ────────

export type StartPayload = {
  type: "start";
  assistant_message_id: string;
  session_id: string;
};

export type FinishPayload = {
  type: "finish";
  reason: string;
  assistant_message_id: string;
};

export type ErrorPayload = {
  type: "error";
  code: string;
  message: string;
};

export type TextDeltaPayload = {
  type: "text_delta";
  kind: "text";
  step: number;
  delta: string;
};

/**
 * Tool packets are emitted as three granular wire events per call
 * (`<tool>_start`, `<tool>_call`, `<tool>_end`), but they all share the same
 * structural shape — only the `type` literal varies. The router collapses
 * them into three handlers (start / call / end) and exposes the tool name
 * separately, so consumers don't have to switch on every tool's literal.
 */
export type ToolStartPayload = {
  type: string; // e.g. "search_memories_start"
  kind: "tool";
  step: number;
  tool_call_id: string;
};

export type ToolCallPayload = {
  type: string; // e.g. "search_memories_call"
  kind: "tool";
  step: number;
  tool_call_id: string;
  arguments: Record<string, unknown>;
};

export type ToolEndPayload = {
  type: string; // e.g. "search_memories_end"
  kind: "tool";
  step: number;
  tool_call_id: string;
  status: ToolEventStatus;
  result: Record<string, unknown> | null;
  error: string | null;
};
