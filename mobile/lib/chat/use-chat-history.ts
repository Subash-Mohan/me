/**
 * History leaf hook — wraps TanStack `useInfiniteQuery` against
 * `GET /sessions/{id}/messages`.
 *
 * Sole responsibility: present persisted messages chronologically + expose
 * pagination + expose a single `commitTurn` setter for the stream hook to
 * call when a turn completes.
 *
 * Doesn't know about streaming, reducers, or the active turn — those live
 * in `use-chat-stream.ts`. The composer wires `commitTurn` into the stream
 * hook's `onTurnComplete` callback.
 */

import {
  type InfiniteData,
  useInfiniteQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

import { useApi } from "@/lib/auth/auth-store";
import type { MessagesPage, ServerMessage } from "@/lib/api/types";

const PAGE_SIZE = 50;

type ChatHistoryQueryKey = readonly ["session", string, "messages"];

function chatHistoryQueryKey(sessionId: string): ChatHistoryQueryKey {
  return ["session", sessionId, "messages"] as const;
}

export type UseChatHistory = {
  /** Persisted messages in chronological order (oldest first). */
  messages: ServerMessage[];
  /** Fetch the next older page. No-op when there's nothing more. */
  fetchOlder: () => void;
  /** True iff there's a next cursor on the most-recently-fetched page. */
  hasOlder: boolean;
  /** Initial load in flight. */
  isLoading: boolean;
  /** Commit one finished user+assistant pair into the cache (newest-first page). */
  commitTurn: (user: ServerMessage, assistant: ServerMessage) => void;
};

export function useChatHistory(sessionId: string | null): UseChatHistory {
  const api = useApi();
  const queryClient = useQueryClient();

  const query = useInfiniteQuery<
    MessagesPage,
    Error,
    InfiniteData<MessagesPage, string | undefined>,
    ChatHistoryQueryKey,
    string | undefined
  >({
    queryKey: sessionId
      ? chatHistoryQueryKey(sessionId)
      : (["session", "__none__", "messages"] as const),
    enabled: sessionId !== null,
    initialPageParam: undefined,
    queryFn: ({ pageParam, signal }) =>
      api.sessions.messages({
        sessionId: sessionId as string, // narrowed by `enabled`
        before: pageParam,
        limit: PAGE_SIZE,
        // sessions.messages doesn't currently accept a signal; not needed
        // because tanstack cancels by abandoning the promise. Kept for
        // future-proofing.
        ...(signal ? {} : {}),
      }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  // Pages arrive newest-first within each page (server-side desc). Older
  // pages come AFTER newer ones in `data.pages`. For chronological display
  // we flatten then reverse so the oldest message is first. Memoised on
  // `query.data` so the reference is stable across renders that don't
  // change history — critical for the composer hook's per-delta memos.
  const messages: ServerMessage[] = useMemo(
    () =>
      query.data
        ? query.data.pages.flatMap((page) => page.items).slice().reverse()
        : [],
    [query.data],
  );

  const fetchOlder = useCallback(() => {
    if (!query.hasNextPage || query.isFetchingNextPage) return;
    void query.fetchNextPage();
  }, [query]);

  const commitTurn = useCallback(
    (user: ServerMessage, assistant: ServerMessage) => {
      if (!sessionId) return;
      queryClient.setQueryData<InfiniteData<MessagesPage, string | undefined>>(
        chatHistoryQueryKey(sessionId),
        (old) => {
          if (!old || old.pages.length === 0) {
            return {
              pages: [
                { items: [assistant, user], next_cursor: null },
              ],
              pageParams: [undefined],
            };
          }
          const [first, ...rest] = old.pages;
          // Drop any stale row a racing GET may have left in the cache with
          // the same id — the freshly-committed pair is authoritative.
          const filtered = first.items.filter(
            (m) => m.id !== user.id && m.id !== assistant.id,
          );
          return {
            ...old,
            pages: [
              { ...first, items: [assistant, user, ...filtered] },
              ...rest,
            ],
          };
        },
      );
    },
    [queryClient, sessionId],
  );

  return {
    messages,
    fetchOlder,
    hasOlder: query.hasNextPage ?? false,
    isLoading: query.isLoading,
    commitTurn,
  };
}
