/**
 * Pure server-shape → render-shape mapping for chat messages.
 *
 * Single responsibility: take a `ServerMessage` (or an in-flight `ActiveTurn`)
 * and return one or two `RenderMessage`s shaped exactly as `MessageBubble`
 * already consumes. The existing `MessageBubble` / `MemoryCard` components
 * stay untouched.
 *
 * No React, no I/O. The composer's `useMemo` calls this whenever inputs
 * change.
 */

import type { ServerEvent, ServerMessage } from "@/lib/api/types";
import type { ActiveTurn, EventState } from "@/lib/chat/reducer";
import { applyToolRenderers } from "@/lib/chat/tool-renderers";
import type { Message as RenderMessage } from "@/lib/types";

export function adaptServerMessage(m: ServerMessage): RenderMessage {
  const timestamp = new Date(m.created_at);
  if (m.role === "user") {
    return {
      id: m.id,
      sender: "user",
      text: m.content,
      timestamp,
    };
  }
  const events = m.events ?? [];
  const contribution = applyToolRenderers(events);
  return {
    id: m.id,
    sender: "ai",
    text: m.content,
    timestamp,
    memoryAdded: contribution.memoryAdded,
  };
}

/**
 * Translate the reducer's in-flight `ActiveTurn` into a `[user, assistant]`
 * pair the screen renders alongside the persisted history.
 *
 * The assistant message's id is `pending:<clientMessageId>` until the
 * `start` packet arrives with the server-allocated id; this synthetic
 * prefix avoids clashing with real UUIDs in any keyed list.
 */
export function adaptActiveTurn(
  turn: ActiveTurn,
): [RenderMessage, RenderMessage] {
  const user: RenderMessage = {
    id: turn.clientMessageId,
    sender: "user",
    text: turn.userText,
    timestamp: turn.startedAt,
  };

  const events = serverEventsFromTurn(turn);
  const contribution = applyToolRenderers(events);
  const text = events
    .filter((e): e is Extract<ServerEvent, { kind: "text" }> => e.kind === "text")
    .map((e) => e.content)
    .join("");

  const assistant: RenderMessage = {
    id: turn.assistantMessageId ?? `pending:${turn.clientMessageId}`,
    sender: "ai",
    text,
    timestamp: turn.startedAt,
    memoryAdded: contribution.memoryAdded,
    isStreaming: turn.status === "streaming",
  };

  return [user, assistant];
}

/**
 * Flatten the reducer's step-keyed events map into a step-sorted list shaped
 * exactly like `ServerMessage.events`. Used by `adaptActiveTurn` and by the
 * caller that commits a finished turn to the query cache.
 */
export function serverEventsFromTurn(turn: ActiveTurn): ServerEvent[] {
  const states = Object.values(turn.events).sort((a, b) => a.step - b.step);
  return states.map(eventStateToServerEvent);
}

function eventStateToServerEvent(state: EventState): ServerEvent {
  if (state.kind === "text") {
    return { step: state.step, kind: "text", content: state.content };
  }
  return {
    step: state.step,
    kind: "tool",
    tool_call_id: state.tool_call_id,
    tool: state.tool,
    arguments: state.arguments,
    status: state.status,
    result: state.result,
    error: state.error,
  };
}

