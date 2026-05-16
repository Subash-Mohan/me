import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createApi, HttpError, resolveBaseUrl, type Api } from "@/lib/api";
import {
  clearSession as clearStored,
  loadSession,
  saveSession,
  type StoredSession,
} from "./session-storage";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  status: AuthStatus;
  session: StoredSession | null;
  api: Api;
  login: (passphrase: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function isExpired(expiresAt: string): boolean {
  const ts = Date.parse(expiresAt);
  if (Number.isNaN(ts)) return true;
  return ts <= Date.now();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [session, setSession] = useState<StoredSession | null>(null);
  const tokenRef = useRef<string | null>(null);
  const verifiedRef = useRef(false);

  tokenRef.current = session?.token ?? null;

  const handleUnauthorized = useCallback(() => {
    if (tokenRef.current === null) return;
    tokenRef.current = null;
    verifiedRef.current = false;
    void clearStored();
    setSession(null);
    setStatus("unauthenticated");
  }, []);

  const api = useMemo<Api>(
    () =>
      createApi({
        baseUrl: resolveBaseUrl(),
        getToken: () => tokenRef.current,
        onUnauthorized: handleUnauthorized,
      }),
    [handleUnauthorized],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = await loadSession();
      if (cancelled) return;
      if (!stored || isExpired(stored.expiresAt)) {
        if (stored) await clearStored();
        setSession(null);
        setStatus("unauthenticated");
        return;
      }
      setSession(stored);
      setStatus("authenticated");
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (status !== "authenticated" || !session || verifiedRef.current) return;
    verifiedRef.current = true;
    let cancelled = false;
    (async () => {
      try {
        await api.auth.me();
      } catch (err) {
        if (cancelled) return;
        if (!(err instanceof HttpError)) {
          // network / parse failure — ignore, don't kick user out
          return;
        }
        // 401 is already handled by onUnauthorized; nothing to do here.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, session, api]);

  const login = useCallback(
    async (passphrase: string) => {
      const res = await api.auth.login(passphrase);
      const next: StoredSession = {
        token: res.access_token,
        expiresAt: res.expires_at,
      };
      await saveSession(next);
      tokenRef.current = next.token;
      verifiedRef.current = true;
      setSession(next);
      setStatus("authenticated");
    },
    [api],
  );

  const logout = useCallback(async () => {
    tokenRef.current = null;
    verifiedRef.current = false;
    await clearStored();
    setSession(null);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, session, api, login, logout }),
    [status, session, api, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return ctx;
}

export function useApi(): Api {
  return useAuth().api;
}
