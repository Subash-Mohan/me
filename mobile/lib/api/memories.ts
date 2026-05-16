/**
 * Memories REST resource — thin wrappers over the generic apiClient.
 *
 * v1: only `list` is wired. Detail / create / update / delete / search are
 * available on the backend (`app/api/memories.py`) but not yet needed by the
 * mobile screens.
 */

import type { ApiClient } from "./client";
import type { MemoryListResponse } from "./types";

export type MemoriesResource = {
  list: (args?: {
    cursor?: string;
    limit?: number;
    from_date?: string;
    to_date?: string;
  }) => Promise<MemoryListResponse>;
};

export function memoriesResource(client: ApiClient): MemoriesResource {
  return {
    list: (args = {}) =>
      client.request<MemoryListResponse>("/memories", {
        query: {
          cursor: args.cursor,
          limit: args.limit,
          from_date: args.from_date,
          to_date: args.to_date,
        },
      }),
  };
}
