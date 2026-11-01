import type { User } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

const KEY = "lf.tokens";
interface Tokens { access_token: string; refresh_token: string }

export const tokenStore = {
  get(): Tokens | null {
    try { return JSON.parse(localStorage.getItem(KEY) ?? "null"); } catch { return null; }
  },
  set(t: Tokens | null) {
    try {
      if (t) localStorage.setItem(KEY, JSON.stringify(t));
      else localStorage.removeItem(KEY);
    } catch { /* private mode */ }
  },
};

let refreshing: Promise<boolean> | null = null;
async function refresh(): Promise<boolean> {
  const t = tokenStore.get();
  if (!t) return false;
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${API_URL}/auth/refresh`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: t.refresh_token }),
      });
      if (!r.ok) { tokenStore.set(null); return false; }
      tokenStore.set(await r.json());
      return true;
    } catch { return false; } finally { setTimeout(() => (refreshing = null), 0); }
  })();
  return refreshing;
}

function message(body: unknown, fallback: string): string {
  const d = (body as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`).join("; ");
  return fallback;
}

export async function request<T = unknown>(path: string, init: RequestInit & { json?: unknown; retry?: boolean } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const t = tokenStore.get();
  if (t) headers.set("Authorization", `Bearer ${t.access_token}`);
  let body = init.body;
  if (init.json !== undefined) { headers.set("Content-Type", "application/json"); body = JSON.stringify(init.json); }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, body });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }
  if (res.status === 401 && t && init.retry !== false && (await refresh())) {
    return request<T>(path, { ...init, retry: false });
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, message(data, res.statusText), data?.code);
  return data as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, json?: unknown) => request<T>(path, { method: "POST", json: json ?? {} }),
  patch: <T,>(path: string, json: unknown) => request<T>(path, { method: "PATCH", json }),
  upload: <T,>(path: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<T>(path, { method: "POST", body: fd });
  },
};

export function imgUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  return path.startsWith("http") ? path : `${API_URL}${path}`;
}

export async function login(email: string, password: string): Promise<User> {
  const r = await request<{ user: User; access_token: string; refresh_token: string }>("/auth/login", {
    method: "POST", json: { email, password }, retry: false,
  });
  tokenStore.set({ access_token: r.access_token, refresh_token: r.refresh_token });
  return r.user;
}
export async function register(name: string, email: string, password: string, phone?: string): Promise<User> {
  const r = await request<{ user: User; access_token: string; refresh_token: string }>("/auth/register", {
    method: "POST", json: { name, email, password, phone: phone || null }, retry: false,
  });
  tokenStore.set({ access_token: r.access_token, refresh_token: r.refresh_token });
  return r.user;
}
export async function logout() {
  const t = tokenStore.get();
  try { if (t) await request("/auth/logout", { method: "POST", json: { refresh_token: t.refresh_token }, retry: false }); } catch { /* ignore */ }
  tokenStore.set(null);
}
