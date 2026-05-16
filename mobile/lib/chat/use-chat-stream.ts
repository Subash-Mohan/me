/**
 * Streaming leaf hook — owns the reducer + abort controller + one SSE call.
 *
 * Sole responsibility: handle `sendMessage(text, sessionId)`. Open the SSE
 * stream, dispatch each incoming packet into the reducer, and on `finish`
 * synthesize the persisted user+assistant pair and hand it to
 * `onTurnComplete` (which the composer wires into the history hook's
 * `commitTurn`).
 *
 * Doesn't know about TanStack Query, the screen, or session bootstrap.
 */

import { useCallback, useEffect, useReducer, useRef } from "react";

import {
  HttpError,
  NetworkError,
  resolveBaseUrl,
  streamChat,
  type PacketHandlers,
} from "@/lib/api";
import { toolNameFromType } from "@/lib/api/packet-router";
import type { ServerMessage } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-store";
import { serverEventsFromTurn } from "@/lib/chat/adapter";
import {
  type ActiveTurn,
  type ChatAction,
  type ChatState,
  initialState,
  reducer,
} from "@/lib/chat/reducer";
import { getTimezone } from "@/lib/chat/timezone";

export type UseChatStream = {
  activeTurn: ActiveTurn | null;
  status: "idle" | "streaming" | "error";
  error: string | null;
  sendMessage: (text: string, sessionId: string) => void;
  stop: () => void;
};

type OnTurnComplete = (
  user: ServerMessage,
  assistant: ServerMessage,
) => void;

export function useChatStream(onTurnComplete: OnTurnComplete): UseChatStream {
  const auth = useAuth();
  const [state, dispatch] = useReducer<ChatState, [ChatAction]>(
    reducer,
    initialState,
  );

  // Mirror the latest active turn into a ref so the SSE handlers — which
  // are created once per send — always read the freshest state when they
  // synthesize the persisted pair on `finish`.
  const activeTurnRef = useRef<ActiveTurn | null>(null);
  useEffect(() => {
    activeTurnRef.current = state.activeTurn;
  }, [state.activeTurn]);

  // Mirror the freshest `onTurnComplete` so callers can update the callback
  // between sends without breaking an in-flight stream.
  const onTurnCompleteRef = useRef(onTurnComplete);
  useEffect(() => {
    onTurnCompleteRef.current = onTurnComplete;
  }, [onTurnComplete]);

  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    dispatch({ type: "turn/clear" });
  }, []);

  // Tear down any in-flight stream when the hook unmounts. Keeps the abort
  // controller from leaking past the screen lifetime.
  useEffect(() => () => abortRef.current?.abort(), []);

  const sendMessage = useCallback(
    (text: string, sessionId: string) => {
      const token = auth.session?.token;
      if (!token) return;
      if (abortRef.current) abortRef.current.abort();

      const clientMessageId = randomUuidV4();
      const startedAt = new Date();
      dispatch({
        type: "turn/start",
        clientMessageId,
        userText: text,
        startedAt,
      });

      const controller = new AbortController();
      abortRef.current = controller;

      const handlers: PacketHandlers = {
        onStart: (p) =>
          dispatch({
            type: "packet/start",
            assistantMessageId: p.assistant_message_id,
          }),
        onTextDelta: (p) =>
          dispatch({
            type: "packet/text_delta",
            step: p.step,
            delta: p.delta,
          }),
        onToolStart: (p) => {
          const tool = toolNameFromType(p.type);
          if (!tool) return;
          dispatch({
            type: "packet/tool_start",
            step: p.step,
            tool_call_id: p.tool_call_id,
            tool,
          });
        },
        onToolCall: (p) => {
          const tool = toolNameFromType(p.type);
          if (!tool) return;
          dispatch({
            type: "packet/tool_call",
            step: p.step,
            tool_call_id: p.tool_call_id,
            tool,
            arguments: p.arguments,
          });
        },
        onToolEnd: (p) => {
          const tool = toolNameFromType(p.type);
          if (!tool) return;
          dispatch({
            type: "packet/tool_end",
            step: p.step,
            tool_call_id: p.tool_call_id,
            tool,
            status: p.status,
            result: p.result ?? null,
            error: p.error ?? null,
          });
        },
        onError: (p) =>
          dispatch({ type: "packet/error", code: p.code, message: p.message }),
        onFinish: (p) => {
          const turn = activeTurnRef.current;
          if (!turn) return;
          const finishedAt = new Date().toISOString();
          const user: ServerMessage = {
            id: turn.clientMessageId,
            role: "user",
            content: turn.userText,
            events: null,
            parent_message_id: null,
            client_tz: getTimezone(),
            created_at: turn.startedAt.toISOString(),
          };
          const events = serverEventsFromTurn(turn);
          const assistant: ServerMessage = {
            id: p.assistant_message_id,
            role: "assistant",
            content: events
              .filter((e) => e.kind === "text")
              .map((e) => (e.kind === "text" ? e.content : ""))
              .join(""),
            events: events.length > 0 ? events : null,
            parent_message_id: turn.clientMessageId,
            client_tz: null,
            created_at: finishedAt,
          };
          onTurnCompleteRef.current(user, assistant);
          dispatch({ type: "turn/clear" });
        },
      };

      const options = {
        token,
        baseUrl: resolveBaseUrl(),
        signal: controller.signal,
      };

      streamChat(
        {
          sessionId,
          clientMessageId,
          message: text,
          clientTz: getTimezone(),
        },
        handlers,
        options,
      ).catch((err) => {
        if (controller.signal.aborted) return; // user-initiated stop
        const message =
          err instanceof HttpError
            ? `HTTP ${err.status}`
            : err instanceof NetworkError
              ? "network failure"
              : err instanceof Error
                ? err.message
                : "unknown error";
        dispatch({ type: "packet/error", code: "stream_failed", message });
      });
    },
    [auth.session?.token],
  );

  const status: "idle" | "streaming" | "error" = state.activeTurn
    ? state.activeTurn.status
    : "idle";

  return {
    activeTurn: state.activeTurn,
    status,
    error: state.activeTurn?.errorMessage ?? null,
    sendMessage,
    stop,
  };
}

// ─── helpers ──────────────────────────────────────────────────────────────

function randomUuidV4(): string {
  // Hermes 0.81 ships `crypto.randomUUID` on most platforms; fall back to a
  // manual v4 generator if it's unavailable.
  const cryptoObj =
    typeof globalThis !== "undefined"
      ? (globalThis as { crypto?: { randomUUID?: () => string } }).crypto
      : undefined;
  if (cryptoObj?.randomUUID) return cryptoObj.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
