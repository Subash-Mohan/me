/**
 * Sessions REST resource — thin wrappers over the generic apiClient.
 *
 * No streaming here; chat SSE lives in `chat-stream.ts`. This module only
 * owns the four CRUD/list operations the chat screen and history hooks need.
 */

import type { ApiClient } from "./client";
import type {
  MessagesPage,
  SessionListResponse,
  SessionRead,
} from "./types";

export type SessionsResource = {
  list: (args?: {
    cursor?: string;
    limit?: number;
  }) => Promise<SessionListResponse>;
  create: (args?: { title?: string | null }) => Promise<SessionRead>;
  detail: (id: string) => Promise<SessionRead>;
  messages: (args: {
    sessionId: string;
    before?: string;
    limit?: number;
  }) => Promise<MessagesPage>;
};

export function sessionsResource(client: ApiClient): SessionsResource {
  return {
    list: (args = {}) =>
      client.request<SessionListResponse>("/sessions", {
        query: { cursor: args.cursor, limit: args.limit },
      }),
    create: (args = {}) =>
      client.request<SessionRead>("/sessions", {
        method: "POST",
        body: { title: args.title ?? null },
      }),
    detail: (id) => client.request<SessionRead>(`/sessions/${id}`),
    messages: ({ sessionId, before, limit }) =>
      client.request<MessagesPage>(`/sessions/${sessionId}/messages`, {
        query: { before, limit },
      }),
  };
}
