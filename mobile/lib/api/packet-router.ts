/**
 * Pure event → handler router for the chat SSE stream.
 *
 * Sole responsibility: given one parsed `{event, data}` pair, parse the
 * JSON payload and invoke the right handler. Knows nothing about transport
 * (no fetch, no abort), nothing about React state.
 *
 * Granular per-tool wire literals like `search_memories_start` /
 * `manage_memory_call` are folded into three coarse handlers (`onToolStart`,
 * `onToolCall`, `onToolEnd`) by branching on the payload's `kind` field —
 * consumers don't enumerate every tool's literal.
 */

import type { SseEvent } from "./sse-parser";
import type {
  ErrorPayload,
  FinishPayload,
  StartPayload,
  TextDeltaPayload,
  ToolCallPayload,
  ToolEndPayload,
  ToolStartPayload,
} from "./types";

export type PacketHandlers = {
  onStart: (p: StartPayload) => void;
  onTextDelta: (p: TextDeltaPayload) => void;
  onToolStart: (p: ToolStartPayload) => void;
  onToolCall: (p: ToolCallPayload) => void;
  onToolEnd: (p: ToolEndPayload) => void;
  onError: (p: ErrorPayload) => void;
  onFinish: (p: FinishPayload) => void;
};

/**
 * Route a single SSE event to the matching handler. Silently drops events
 * with malformed JSON or unrecognized envelope/tool shape — the stream is
 * untrusted at the parser boundary, but at this layer we trust the server.
 */
export function routePacket(event: SseEvent, handlers: PacketHandlers): void {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(event.data) as Record<string, unknown>;
  } catch {
    return;
  }

  switch (event.event) {
    case "start":
      handlers.onStart(payload as unknown as StartPayload);
      return;
    case "finish":
      handlers.onFinish(payload as unknown as FinishPayload);
      return;
    case "error":
      handlers.onError(payload as unknown as ErrorPayload);
      return;
    case "text_delta":
      handlers.onTextDelta(payload as unknown as TextDeltaPayload);
      return;
  }

  // Tool packets share a structural shape; the granular `type` literal lives
  // on the payload (e.g. "search_memories_start"). The phase (start/call/end)
  // is the suffix.
  if (payload.kind !== "tool") return;

  if (event.event.endsWith("_start")) {
    handlers.onToolStart(payload as unknown as ToolStartPayload);
  } else if (event.event.endsWith("_call")) {
    handlers.onToolCall(payload as unknown as ToolCallPayload);
  } else if (event.event.endsWith("_end")) {
    handlers.onToolEnd(payload as unknown as ToolEndPayload);
  }
}

/**
 * Extract the tool name from a tool packet's wire `type` literal, e.g.
 * `"search_memories_start"` → `"search_memories"`. Returns `null` if the
 * literal doesn't match the expected `<tool>_<start|call|end>` shape.
 */
export function toolNameFromType(type: string): string | null {
  for (const suffix of ["_start", "_call", "_end"] as const) {
    if (type.endsWith(suffix)) return type.slice(0, -suffix.length);
  }
  return null;
}
