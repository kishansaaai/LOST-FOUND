"use client";
import { useEffect, useRef, useState } from "react";
import type { ApiError } from "@/lib/api";

/** Minimal data hook. Loading is *derived* (the result belongs to a different request key than the current one),
 *  so there is no synchronous setState inside effects; stale responses are ignored; `reload()` bumps a nonce. */
export function useQuery<T>(fn: () => Promise<T>, deps: unknown[], enabled = true) {
  const [nonce, setNonce] = useState(0);
  const [res, setRes] = useState<{ key: string; data: T | null; error: ApiError | Error | null }>({ key: "", data: null, error: null });
  const latest = useRef(fn);
  useEffect(() => { latest.current = fn; });
  const key = `${JSON.stringify(deps)}#${nonce}`;

  useEffect(() => {
    if (!enabled) return;
    let stale = false;
    latest.current().then(
      (data) => { if (!stale) setRes({ key, data, error: null }); },
      (error) => { if (!stale) setRes((r) => ({ key, data: r.data, error })); },
    );
    return () => { stale = true; };
  }, [key, enabled]);

  const current = res.key === key;
  return { data: res.data, error: current ? res.error : null, loading: enabled && !current, reload: () => setNonce((n) => n + 1) };
}
