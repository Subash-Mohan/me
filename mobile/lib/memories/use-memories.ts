/**
 * Memories list hook — wraps TanStack `useInfiniteQuery` against
 * `GET /memories`.
 *
 * The backend returns one cursor-paginated page newest-first (server orders
 * by `(event_date DESC, id DESC)`); the hook flattens pages into a single
 * chronologically newest-first array shaped for the logs screen.
 */

import { type InfiniteData, useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

import type { MemoryListResponse } from "@/lib/api/types";
import { useApi } from "@/lib/auth/auth-store";
import type { MemoryCard } from "@/lib/types";

import { adaptServerMemoryCard } from "./adapter";

const PAGE_SIZE = 50;
const KEY = ["memories", "list"] as const;

export type UseMemories = {
  memories: MemoryCard[];
  fetchOlder: () => void;
  hasOlder: boolean;
  isLoading: boolean;
  isFetchingOlder: boolean;
  error: Error | null;
};

export function useMemories(): UseMemories {
  const api = useApi();

  const query = useInfiniteQuery<
    MemoryListResponse,
    Error,
    InfiniteData<MemoryListResponse, string | undefined>,
    typeof KEY,
    string | undefined
  >({
    queryKey: KEY,
    initialPageParam: undefined,
    queryFn: ({ pageParam }) =>
      api.memories.list({ cursor: pageParam, limit: PAGE_SIZE }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const memories = useMemo(
    () =>
      query.data
        ? query.data.pages.flatMap((p) => p.items).map(adaptServerMemoryCard)
        : [],
    [query.data],
  );

  const fetchOlder = useCallback(() => {
    if (!query.hasNextPage || query.isFetchingNextPage) return;
    void query.fetchNextPage();
  }, [query]);

  return {
    memories,
    fetchOlder,
    hasOlder: query.hasNextPage ?? false,
    isLoading: query.isLoading,
    isFetchingOlder: query.isFetchingNextPage,
    error: query.error,
  };
}
