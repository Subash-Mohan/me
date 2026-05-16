import { authResource, type AuthResource } from "./auth";
import { createApiClient, type ApiClientConfig } from "./client";

export type Api = {
  auth: AuthResource;
};

export function createApi(config: ApiClientConfig): Api {
  const client = createApiClient(config);
  return {
    auth: authResource(client),
  };
}

export { HttpError, NetworkError } from "./errors";
export { resolveBaseUrl } from "./config";
export type { ApiClient, ApiClientConfig, RequestOptions } from "./client";
