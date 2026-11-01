"use client";
import Link from "next/link";
import { Plus, Sparkles } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "@/components/states";
import { ItemThumb } from "@/components/item-card";
import { StatusBadge } from "@/components/status-badge";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import type { Item } from "@/lib/types";

export default function MyItems() {
  const { allowed } = useRequireAuth();
  const q = useQuery(() => api.get<{ items: Item[] }>("/items/mine"), [], allowed);
  if (!allowed) return null;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="My reports" description="Everything you reported, and any matches waiting for you." actions={<Link href="/report" className={buttonVariants()}><Plus className="size-4" />New report</Link>} />
      {q.loading ? <ListSkeleton /> : q.error ? <ErrorState error={q.error} retry={q.reload} /> : !q.data?.items.length ? (
        <EmptyState title="You have not reported anything yet" hint="Lost something or found something? Add a report and we will start matching." action={<Link href="/report" className={buttonVariants()}>Report an item</Link>} />
      ) : (
        <ul className="space-y-4">{q.data.items.map((i) => (
          <li key={i.item_id}><Link href={`/items/${i.item_id}`} className="flex gap-4 rounded-lg border bg-card p-4 transition hover:bg-muted/50">
            <ItemThumb item={i} className="size-20 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="font-medium">{i.title}</span><StatusBadge value={i.item_type} /><StatusBadge value={i.status} /></div>
              <p className="mt-1 text-sm text-muted-foreground">{i.location_name} · {fmtDate(i.date_lost_or_found)}</p>
              {!!i.suggested_matches && <p className="mt-1 flex items-center gap-1 text-sm font-medium text-primary"><Sparkles className="size-3.5" />{i.suggested_matches} suggested match{i.suggested_matches === 1 ? "" : "es"}</p>}</div>
          </Link></li>))}</ul>)}
    </div>
  );
}
