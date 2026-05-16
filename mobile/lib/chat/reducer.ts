/**
 * Pure state machine for the in-flight assistant turn.
 *
 * Sole responsibility: given the previous state and one action, return the
 * next state. No React, no I/O. Easy to unit-test with scripted action
 * sequences.
 *
 * `packet/finish` is intentionally absent — finishing a turn is a multi-step
 * operation (commit to query cache, then clear), and the caller drives both
 * imperatively so the cache write and the reducer reset cannot race.
 */

export type TextEventState = {
  step: number;
  kind: "text";
  content: string;
};

export type ToolEventState = {
  step: number;
  kind: "tool";
  tool_call_id: string;
  tool: string;
  arguments: Record<string, unknown> | null;
  status: "ok" | "error" | null;
  result: Record<string, unknown> | null;
  error: string | null;
};

export type EventState = TextEventState | ToolEventState;

export type ActiveTurn = {
  clientMessageId: string;
  assistantMessageId: string | null;
  userText: string;
  startedAt: Date;
  events: Record<number, EventState>;
  status: "streaming" | "error";
  errorMessage: string | null;
};

export type ChatState = {
  activeTurn: ActiveTurn | null;
};

export type ChatAction =
  | {
      type: "turn/start";
      clientMessageId: string;
      userText: string;
      startedAt: Date;
    }
  | { type: "packet/start"; assistantMessageId: string }
  | { type: "packet/text_delta"; step: number; delta: string }
  | {
      type: "packet/tool_start";
      step: number;
      tool_call_id: string;
      tool: string;
    }
  | {
      type: "packet/tool_call";
      step: number;
      tool_call_id: string;
      tool: string;
      arguments: Record<string, unknown>;
    }
  | {
      type: "packet/tool_end";
      step: number;
      tool_call_id: string;
      tool: string;
      status: "ok" | "error";
      result?: Record<string, unknown> | null;
      error?: string | null;
    }
  | { type: "packet/error"; code: string; message: string }
  | { type: "turn/clear" };

export const initialState: ChatState = { activeTurn: null };

export function reducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "turn/start":
      return {
        activeTurn: {
          clientMessageId: action.clientMessageId,
          assistantMessageId: null,
          userText: action.userText,
          startedAt: action.startedAt,
          events: {},
          status: "streaming",
          errorMessage: null,
        },
      };

    case "packet/start": {
      const turn = state.activeTurn;
      if (!turn) return state;
      return {
        activeTurn: { ...turn, assistantMessageId: action.assistantMessageId },
      };
    }

    case "packet/text_delta": {
      const turn = state.activeTurn;
      if (!turn) return state;
      const existing = turn.events[action.step];
      const nextEvent: TextEventState =
        existing && existing.kind === "text"
          ? { ...existing, content: existing.content + action.delta }
          : { step: action.step, kind: "text", content: action.delta };
      return {
        activeTurn: {
          ...turn,
          events: { ...turn.events, [action.step]: nextEvent },
        },
      };
    }

    case "packet/tool_start":
    case "packet/tool_call":
    case "packet/tool_end": {
      const turn = state.activeTurn;
      if (!turn) return state;
      const existing = turn.events[action.step];
      const base: ToolEventState =
        existing && existing.kind === "tool"
          ? existing
          : {
              step: action.step,
              kind: "tool",
              tool_call_id: action.tool_call_id,
              tool: action.tool,
              arguments: null,
              status: null,
              result: null,
              error: null,
            };
      const next =
        action.type === "packet/tool_call"
          ? { ...base, arguments: action.arguments }
          : action.type === "packet/tool_end"
            ? {
                ...base,
                status: action.status,
                result: action.result ?? null,
                error: action.error ?? null,
              }
            : base;
      return {
        activeTurn: {
          ...turn,
          events: { ...turn.events, [action.step]: next },
        },
      };
    }

    case "packet/error": {
      const turn = state.activeTurn;
      if (!turn) return state;
      return {
        activeTurn: { ...turn, status: "error", errorMessage: action.message },
      };
    }

    case "turn/clear":
      return initialState;
  }
}
