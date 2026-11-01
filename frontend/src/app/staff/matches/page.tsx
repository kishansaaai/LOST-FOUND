"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "@/components/states";
import { ItemThumb } from "@/components/item-card";
import { StatusBadge } from "@/components/status-badge";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { fmtDate, pct } from "@/lib/format";

interface M { match_id: number; verification_status: string; rrf_score: number; boost: number; text_score: number | null; image_score: number | null; text_rank: number | null; image_rank: number | null;
  lost_item_id: number; lost_title: string; lost_images: string[]; lost_location: string; lost_date: string;
  found_item_id: number; found_title: string; found_images: string[]; found_location: string; found_date: string }

export default function Matches() {
  const [status, setStatus] = useState("suggested");
  const q = useQuery(() => api.get<{ matches: M[]; total: number }>(`/staff/matches?status=${status}&page_size=50`), [status]);
  async function decide(id: number, kind: "confirm" | "reject") {
    try { await api.post(`/staff/matches/${id}/${kind}`); toast.success(kind === "confirm" ? "Match confirmed" : "Match rejected"); q.reload(); } catch (e) { toast.error((e as Error).message); }
  }
  const Side = ({ title, images, loc, date, id, tag }: { title: string; images: string[]; loc: string; date: string; id: number; tag: string }) => (
    <Link href={`/items/${id}`} className="flex min-w-0 flex-1 gap-3"><ItemThumb item={{ image_urls: images, title }} className="size-16 shrink-0 rounded-lg" />
      <div className="min-w-0"><StatusBadge value={tag} /><div className="mt-1 truncate font-medium">{title}</div><div className="truncate text-xs text-muted-foreground">{loc} · {fmtDate(date)}</div></div></Link>);
  return (
    <div>
      <PageHeader title="Suggested matches" description="Confirming a match marks both reports as matched and withdraws competing suggestions." />
      <Tabs value={status} onValueChange={(v) => setStatus(v as string)} className="mb-4"><TabsList>{["suggested", "confirmed", "rejected"].map((s) => <TabsTrigger key={s} value={s} className="capitalize">{s}</TabsTrigger>)}</TabsList></Tabs>
      {q.loading ? <ListSkeleton /> : q.error ? <ErrorState error={q.error} retry={q.reload} /> : !q.data?.matches.length ? <EmptyState title={`No ${status} matches`} /> : (
        <><p className="mb-2 text-sm text-muted-foreground">{q.data.total} total{q.data.total > 50 ? " (showing the strongest 50)" : ""}</p>
          <ul className="space-y-3">{q.data.matches.map((m) => (
            <li key={m.match_id} className="rounded-xl border bg-card p-4"><div className="flex flex-wrap items-center gap-4">
              <Side title={m.lost_title} images={m.lost_images} loc={m.lost_location} date={m.lost_date} id={m.lost_item_id} tag="lost" /><ArrowRight className="hidden size-4 shrink-0 text-muted-foreground sm:block" />
              <Side title={m.found_title} images={m.found_images} loc={m.found_location} date={m.found_date} id={m.found_item_id} tag="found" />
              <div className="tabular w-full text-xs text-muted-foreground sm:w-auto sm:text-right"><div className="text-base font-semibold text-foreground">{m.rrf_score.toFixed(4)}</div>RRF · text {pct(m.text_score)}{m.text_rank && ` #${m.text_rank}`}<br />image {pct(m.image_score)}{m.image_rank && ` #${m.image_rank}`}</div>
              {m.verification_status === "suggested" && <div className="flex gap-2"><Button size="sm" onClick={() => decide(m.match_id, "confirm")}><Check className="size-4" />Confirm</Button><Button size="sm" variant="outline" onClick={() => decide(m.match_id, "reject")}><X className="size-4" />Reject</Button></div>}
            </div></li>))}</ul></>)}
    </div>
  );
}
