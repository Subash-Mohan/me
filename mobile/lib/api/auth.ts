import type { ApiClient } from "./client";

export type LoginResponse = {
  access_token: string;
  token_type: string;
  expires_at: string;
};

export type MeResponse = {
  id: string;
  created_at: string;
};

export type AuthResource = {
  login: (passphrase: string) => Promise<LoginResponse>;
  me: () => Promise<MeResponse>;
  verifyPassphrase: (passphrase: string) => Promise<void>;
};

export function authResource(client: ApiClient): AuthResource {
  return {
    login: (passphrase) =>
      client.request<LoginResponse>("/auth/login", {
        method: "POST",
        body: { passphrase },
      }),
    me: () => client.request<MeResponse>("/auth/me"),
    verifyPassphrase: (passphrase) =>
      client.request<void>("/auth/verify-passphrase", {
        method: "POST",
        body: { passphrase },
      }),
  };
}
