"use client";
import Link from "next/link";
import { Clock, Users } from "lucide-react";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "@/components/states";
import { ItemThumb } from "@/components/item-card";
import { StatusBadge } from "@/components/status-badge";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import type { QueueClaim } from "@/lib/types";

export default function Queue() {
  const q = useQuery(() => api.get<{ claims: QueueClaim[] }>("/staff/claims/queue"), []);
  return (
    <div>
      <PageHeader title="Claim verification queue" description="Oldest first. Open a claim to compare the proof with the item." />
      {q.loading ? <ListSkeleton /> : q.error ? <ErrorState error={q.error} retry={q.reload} /> : !q.data?.claims.length ? <EmptyState title="Queue is empty" hint="New claims will appear here as they are submitted." /> : (
        <ul className="space-y-3">{q.data.claims.map((c) => (
          <li key={c.claim_id}><Link href={`/staff/claims/${c.claim_id}`} className="flex gap-4 rounded-xl border bg-card p-4 transition hover:bg-muted/50">
            <ItemThumb item={{ image_urls: c.item_images, title: c.item_title }} className="size-20 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{c.item_title}</span><StatusBadge value={c.verification_status} />
                {c.competing_claims > 1 && <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-500/20 dark:text-amber-200"><Users className="size-3" />{c.competing_claims} competing · #{c.queue_position} in line</span>}</div>
              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">“{c.proof_description}”</p>
              <p className="mt-1 flex items-center gap-3 text-xs text-muted-foreground"><span>{c.claimant_name}</span><span className="flex items-center gap-1"><Clock className="size-3" />{timeAgo(c.submitted_at)}</span>{c.match_rrf_score != null && <span>linked match</span>}</p>
            </div></Link></li>))}</ul>)}
    </div>
  );
}
