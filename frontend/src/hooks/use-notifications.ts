"use client";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { API_URL, api, tokenStore } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Unread counter kept live by Server-Sent Events (Redis pub/sub on the server), with a
 *  slow poll as a safety net. fetch() streaming is used because EventSource cannot send headers. */
export function useNotificationCount() {
  const { user } = useAuth();
  const [count, setCount] = useState(0);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!user) return;
    let alive = true;
    const refresh = () => api.get<{ unread: number }>("/notifications/unread-count").then((r) => alive && setCount(r.unread)).catch(() => {});
    refresh();
    const poll = setInterval(refresh, 45000);

    async function connect() {
      while (alive) {
        const t = tokenStore.get();
        if (!t) return;
        abort.current = new AbortController();
        try {
          const res = await fetch(`${API_URL}/notifications/stream`, {
            headers: { Authorization: `Bearer ${t.access_token}` }, signal: abort.current.signal,
          });
          if (!res.ok || !res.body) throw new Error("stream refused");
          const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
          let buf = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += value;
            const parts = buf.split("\n\n");
            buf = parts.pop() ?? "";
            for (const p of parts) {
              const data = p.split("\n").find((l) => l.startsWith("data: "));
              if (data) {
                try { const n = JSON.parse(data.slice(6)); toast(n.title, { description: n.body }); } catch { /* ignore */ }
                refresh();
              }
            }
          }
        } catch { /* reconnect below */ }
        await new Promise((r) => setTimeout(r, 4000));
      }
    }
    connect();
    return () => { alive = false; clearInterval(poll); abort.current?.abort(); };
  }, [user]);

  return { count: user ? count : 0 };
}
