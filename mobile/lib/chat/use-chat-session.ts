/**
 * Session bootstrap leaf hook.
 *
 * Sole responsibility: answer "do we have a session yet, and if not create
 * one." Knows nothing about messages, streaming, reducers, or the query cache.
 *
 * In v1 we hold one active session id in local component state. The future
 * multi-session sidebar will replace this with a hook backed by the
 * sessions query + a "selected session id" piece of state.
 */

import { useCallback, useRef, useState } from "react";

import { useApi } from "@/lib/auth/auth-store";

export type UseChatSession = {
  sessionId: string | null;
  ensureSession: () => Promise<string>;
  /** Drop the active session id so the next send creates a fresh one. */
  clearSession: () => void;
};

export function useChatSession(): UseChatSession {
  const api = useApi();
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Coalesce concurrent ensureSession() calls so we only POST once even if
  // the user double-taps send before the first response lands.
  const inflight = useRef<Promise<string> | null>(null);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId;
    if (inflight.current) return inflight.current;
    let promise: Promise<string>;
    promise = api.sessions
      .create({})
      .then((row) => {
        // If clearSession nulled inflight while we were awaiting, abandon
        // the result — caller's stream-open will reject and be ignored.
        if (inflight.current !== promise) {
          throw new Error("session creation superseded");
        }
        setSessionId(row.id);
        return row.id;
      })
      .finally(() => {
        if (inflight.current === promise) inflight.current = null;
      });
    inflight.current = promise;
    return promise;
  }, [api, sessionId]);

  const clearSession = useCallback(() => {
    inflight.current = null;
    setSessionId(null);
  }, []);

  return { sessionId, ensureSession, clearSession };
}
