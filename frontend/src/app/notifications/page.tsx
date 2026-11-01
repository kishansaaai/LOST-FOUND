"use client";
import Link from "next/link";
import { Bell, CheckCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "@/components/states";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { timeAgo } from "@/lib/format";
import type { Notification } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function Notifications() {
  const { allowed } = useRequireAuth();
  const q = useQuery(() => api.get<{ notifications: Notification[]; unread: number }>("/notifications"), [], allowed);
  if (!allowed) return null;
  async function readAll() { try { await api.post("/notifications/read-all"); q.reload(); } catch (e) { toast.error((e as Error).message); } }
  async function readOne(id: string) { try { await api.post(`/notifications/${id}/read`); q.reload(); } catch { /* ignore */ } }
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Notifications" description={q.data ? `${q.data.unread} unread` : undefined} actions={<Button variant="outline" size="sm" onClick={readAll} disabled={!q.data?.unread}><CheckCheck className="size-4" />Mark all read</Button>} />
      {q.loading && !q.data ? <ListSkeleton /> : q.error ? <ErrorState error={q.error} retry={q.reload} /> : !q.data?.notifications.length ? (
        <EmptyState title="You are all caught up" hint="Match suggestions and claim updates will show up here." />
      ) : <ul className="space-y-2">{q.data.notifications.map((n) => {
        const body = (<><div className="flex items-start gap-3"><span className={cn("mt-0.5 grid size-8 shrink-0 place-items-center rounded-full", n.read ? "bg-muted text-muted-foreground" : "bg-primary/10 text-primary")}><Bell className="size-4" /></span>
          <div className="min-w-0 flex-1"><div className="flex items-baseline justify-between gap-2"><span className={cn("font-medium", n.read && "text-muted-foreground")}>{n.title}</span><time className="shrink-0 text-xs text-muted-foreground">{timeAgo(n.created_at)}</time></div><p className="text-sm text-muted-foreground">{n.body}</p></div>
          {!n.read && <span className="mt-2 size-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}</div></>);
        return <li key={n.id}>{n.link ? <Link href={n.link} onClick={() => readOne(n.id)} className="block rounded-xl border bg-card p-4 transition hover:bg-muted/50">{body}</Link> : <div className="rounded-xl border bg-card p-4">{body}</div>}</li>;
      })}</ul>}
    </div>
  );
}
