"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import * as client from "./api";
import { api, tokenStore } from "./api";
import type { Role, User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (name: string, email: string, password: string, phone?: string) => Promise<User>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
  isStaff: boolean;
}
const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    if (!tokenStore.get()) { setUser(null); setLoading(false); return; }
    try { setUser(await api.get<User>("/auth/me")); } catch { setUser(null); }
    setLoading(false);
  }, []);
  // deferred so the state updates are not synchronous inside the effect body
  useEffect(() => { queueMicrotask(reload); }, [reload]);

  const value = useMemo<AuthState>(() => ({
    user, loading, reload,
    isStaff: user?.role === "staff" || user?.role === "admin",
    login: async (e, p) => { const u = await client.login(e, p); setUser(u); return u; },
    register: async (n, e, p, ph) => { const u = await client.register(n, e, p, ph); setUser(u); return u; },
    logout: async () => { await client.logout(); setUser(null); },
  }), [user, loading, reload]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

/** Redirects to /login when signed out, and to / when the role is insufficient. */
export function useRequireAuth(role?: Role | "staff") {
  const auth = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (auth.loading) return;
    if (!auth.user) router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    else if (role === "staff" && !auth.isStaff) router.replace("/");
    else if (role === "admin" && auth.user.role !== "admin") router.replace("/");
  }, [auth.loading, auth.user, auth.isStaff, role, router]);
  const allowed = !!auth.user && (role === undefined || (role === "staff" ? auth.isStaff : auth.user.role === role));
  return { ...auth, allowed };
}
