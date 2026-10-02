import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getSession, setSession, setUnauthorizedHandler } from "./api";

export type SessionResponse = { access_token: string; expires_at: string; user: { username: string } };

type AuthCtx = {
  username: string | null;
  login: (u: string, p: string) => Promise<void>;
  signup: (u: string, p: string) => Promise<void>;
  logout: (everywhere?: boolean) => void;
  applySession: (r: SessionResponse) => void;
};

const Ctx = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(() => getSession()?.username ?? null);

  const applySession = useCallback((r: SessionResponse) => {
    setSession({ token: r.access_token, expiresAt: r.expires_at, username: r.user.username });
    setUsername(r.user.username);
  }, []);

  const logout = useCallback((everywhere = false) => {
    api(`/api/auth/logout${everywhere ? "?everywhere=true" : ""}`, { method: "POST" }).catch(() => {});
    setSession(null);
    setUsername(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setUsername(null));
    // proactively sign out when the token expires while the tab is open
    const t = setInterval(() => { if (username && !getSession()) setUsername(null); }, 30000);
    return () => clearInterval(t);
  }, [username]);

  const login = useCallback(async (u: string, p: string) => {
    applySession(await api<SessionResponse>("/api/auth/login", { method: "POST", json: { username: u, password: p } }));
  }, [applySession]);

  const signup = useCallback(async (u: string, p: string) => {
    applySession(await api<SessionResponse>("/api/auth/signup", { method: "POST", json: { username: u, password: p } }));
  }, [applySession]);

  const value = useMemo(() => ({ username, login, signup, logout, applySession }), [username, login, signup, logout, applySession]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
