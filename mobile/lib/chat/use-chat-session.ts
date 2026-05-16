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
    const promise = api.sessions
      .create({})
      .then((row) => {
        setSessionId(row.id);
        return row.id;
      })
      .finally(() => {
        inflight.current = null;
      });
    inflight.current = promise;
    return promise;
  }, [api, sessionId]);

  return { sessionId, ensureSession };
}
