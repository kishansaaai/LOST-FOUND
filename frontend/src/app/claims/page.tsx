"use client";
import Link from "next/link";
import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "@/components/states";
import { ItemThumb } from "@/components/item-card";
import { StatusBadge } from "@/components/status-badge";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import type { Claim } from "@/lib/types";

const STEPS = ["Submitted", "Under review", "Decision"];
function Progress({ c }: { c: Claim }) {
  const at = c.result !== "pending" ? 2 : c.verification_status === "under_review" ? 1 : 0;
  return (
    <ol className="mt-3 flex items-center gap-2 text-xs" aria-label="Claim progress">
      {STEPS.map((s, i) => {
        const done = i < at || (i === 2 && c.result !== "pending"), cur = i === at;
        const Icon = i === 2 && c.result === "denied" ? XCircle : done || (cur && i === 2 && c.result === "approved") ? CheckCircle2 : Clock;
        return <li key={s} className="flex items-center gap-2"><span className={`flex items-center gap-1 ${done || cur ? "font-medium text-foreground" : "text-muted-foreground"}`}><Icon className={`size-4 ${c.result === "denied" && i === 2 ? "text-rose-600" : done ? "text-emerald-600" : ""}`} />{i === 2 && c.result !== "pending" ? (c.result === "approved" ? "Approved" : "Not approved") : s}</span>{i < 2 && <span className="h-px w-6 bg-border" />}</li>;
      })}
    </ol>
  );
}

export default function Claims() {
  const { allowed } = useRequireAuth();
  const q = useQuery(() => api.get<{ claims: Claim[] }>("/claims/mine"), [], allowed);
  if (!allowed) return null;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="My claims" description="Track the verification of items you claimed." />
      {q.loading ? <ListSkeleton n={3} /> : q.error ? <ErrorState error={q.error} retry={q.reload} /> : !q.data?.claims.length ? (
        <EmptyState title="No claims yet" hint="When a found item looks like yours, open it and choose “Claim this item”." />
      ) : <ul className="space-y-3">{q.data.claims.map((c) => (
        <li key={c.claim_id} className="rounded-xl border bg-card p-4">
          <div className="flex gap-4"><ItemThumb item={{ image_urls: c.item_images, title: c.item_title }} className="size-16 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><Link href={`/items/${c.item_id}`} className="font-medium hover:underline">{c.item_title}</Link><StatusBadge value={c.result === "pending" ? c.verification_status : c.result} /></div>
              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">“{c.proof_description}”</p><p className="mt-1 text-xs text-muted-foreground">Submitted {fmtDate(c.submitted_at)}</p></div></div>
          <Progress c={c} />
          {c.notes && <p className="mt-3 rounded-lg bg-muted px-3 py-2 text-sm"><span className="font-medium">Staff note: </span>{c.notes}</p>}
        </li>))}</ul>}
    </div>
  );
}
