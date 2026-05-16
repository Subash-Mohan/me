import { HttpError, NetworkError } from "./errors";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export type QueryValue = string | number | boolean | null | undefined;

export type RequestOptions = {
  method?: HttpMethod;
  body?: unknown;
  query?: Record<string, QueryValue>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

export type ApiClient = {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
};

export type ApiClientConfig = {
  baseUrl: string;
  getToken?: () => string | null | undefined;
  onUnauthorized?: () => void;
};

function buildUrl(
  baseUrl: string,
  path: string,
  query: Record<string, QueryValue> | undefined,
): string {
  const base = path.startsWith("http") ? path : `${baseUrl}${path}`;
  if (!query) return base;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue;
    params.append(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

async function parseDetail(res: Response): Promise<unknown> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return body?.detail ?? body;
  } catch {
    return null;
  }
}

export function createApiClient(config: ApiClientConfig): ApiClient {
  async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    const { method = "GET", body, query, headers = {}, signal } = opts;

    const url = buildUrl(config.baseUrl, path, query);

    const finalHeaders: Record<string, string> = {
      accept: "application/json",
      ...headers,
    };
    if (body !== undefined && finalHeaders["content-type"] === undefined) {
      finalHeaders["content-type"] = "application/json";
    }
    const token = config.getToken?.();
    if (token && finalHeaders.authorization === undefined) {
      finalHeaders.authorization = `Bearer ${token}`;
    }

    let res: Response;
    try {
      res = await fetch(url, {
        method,
        headers: finalHeaders,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
      });
    } catch (err) {
      throw new NetworkError(err);
    }

    if (res.status === 401) {
      config.onUnauthorized?.();
    }

    if (res.status === 204) return undefined as T;

    if (!res.ok) {
      const detail = await parseDetail(res);
      throw new HttpError(res.status, detail);
    }

    try {
      return (await res.json()) as T;
    } catch (err) {
      throw new HttpError(res.status, err);
    }
  }

  return { request };
}
