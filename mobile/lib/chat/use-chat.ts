/**
 * Composer hook — the only hook the chat screen imports.
 *
 * Wires the three single-concern leaf hooks (session bootstrap, history
 * query, streaming reducer) together and exposes a screen-facing surface.
 * Knows nothing about how any of its parts work — only how to compose them.
 *
 * Performance note: history adaptation is memoised on `history.messages`
 * so streaming deltas don't rebuild every persisted `RenderMessage`. The
 * combined `messages` memo only re-runs when history changes or when the
 * in-flight `activeTurn` changes — and during streaming the per-chunk
 * rebuild only adapts the in-flight pair (2 entries), not the full history.
 */

import { useCallback, useMemo } from "react";

import { adaptActiveTurn, adaptServerMessage } from "@/lib/chat/adapter";
import type { Message as RenderMessage } from "@/lib/types";
import { useChatHistory } from "./use-chat-history";
import { useChatSession } from "./use-chat-session";
import { useChatStream } from "./use-chat-stream";

export type UseChat = {
  sessionId: string | null;
  messages: RenderMessage[];
  status: "idle" | "streaming" | "error";
  error: string | null;
  sendMessage: (text: string) => void;
  stop: () => void;
  fetchOlder: () => void;
  hasOlder: boolean;
  isLoadingHistory: boolean;
};

export function useChat(): UseChat {
  const { sessionId, ensureSession } = useChatSession();
  const history = useChatHistory(sessionId);
  const stream = useChatStream(history.commitTurn);

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (trimmed.length === 0) return;
      void (async () => {
        const id = await ensureSession();
        stream.sendMessage(trimmed, id);
      })();
    },
    [ensureSession, stream],
  );

  // History stays stable across deltas — it only changes on page load or
  // when a turn commits to the cache on `finish`. The adapted result is
  // memoised separately so all the history bubbles' `RenderMessage` refs
  // stay identical during streaming, which `React.memo` on `MessageBubble`
  // then uses to skip reconciliation.
  const historyMessages = useMemo(
    () => history.messages.map(adaptServerMessage),
    [history.messages],
  );

  // The in-flight pair is appended fresh whenever `activeTurn` changes
  // (per chunk during streaming). Inlined into this memo since memoising
  // it on its own buys nothing — the dependency would invalidate at the
  // same time as this one.
  const messages = useMemo(
    () =>
      stream.activeTurn
        ? [...historyMessages, ...adaptActiveTurn(stream.activeTurn)]
        : historyMessages,
    [historyMessages, stream.activeTurn],
  );

  return {
    sessionId,
    messages,
    status: stream.status,
    error: stream.error,
    sendMessage,
    stop: stream.stop,
    fetchOlder: history.fetchOlder,
    hasOlder: history.hasOlder,
    isLoadingHistory: history.isLoading,
  };
}
