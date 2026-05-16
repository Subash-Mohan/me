import { authResource, type AuthResource } from "./auth";
import { createApiClient, type ApiClientConfig } from "./client";
import { sessionsResource, type SessionsResource } from "./sessions";

export type Api = {
  auth: AuthResource;
  sessions: SessionsResource;
};

export function createApi(config: ApiClientConfig): Api {
  const client = createApiClient(config);
  return {
    auth: authResource(client),
    sessions: sessionsResource(client),
  };
}

export { HttpError, NetworkError } from "./errors";
export { resolveBaseUrl } from "./config";
export type { ApiClient, ApiClientConfig, RequestOptions } from "./client";
export { streamChat } from "./chat-stream";
export type { PacketHandlers } from "./packet-router";
