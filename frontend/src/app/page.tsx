"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, BadgeCheck, Search, Sparkles, Camera, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CardGridSkeleton, ErrorState } from "@/components/states";
import { ItemCard } from "@/components/item-card";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import type { Item } from "@/lib/types";

interface Stats { open_lost: number; open_found: number; returned: number; recovery_rate_pct: number | null }

export default function Home() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const stats = useQuery(() => api.get<Stats>("/stats"), []);
  const latest = useQuery(() => api.get<{ items: Item[] }>("/items?item_type=found&page_size=8"), []);

  return (
    <div className="space-y-20 sm:space-y-28">
      <section className="mx-auto max-w-3xl pt-4 text-center sm:pt-10">
        <p className="eyebrow mb-6">Text and photo matching</p>
        <h1 className="text-balance text-4xl font-light leading-[1.1] tracking-tight sm:text-6xl">Lost something? Let&apos;s find it together.</h1>
        <p className="mx-auto mt-6 max-w-xl text-balance leading-relaxed text-muted-foreground">Report what you lost or found. We compare descriptions and photos with every open report and tell you the moment something lines up.</p>
        <form className="mx-auto mt-10 flex max-w-xl flex-col gap-3 sm:flex-row" onSubmit={(e) => { e.preventDefault(); router.push(`/items?q=${encodeURIComponent(q)}`); }} role="search">
          <div className="relative flex-1"><Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" strokeWidth={1.5} />
            <Input aria-label="Search items" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Black wallet, backpack, keys" className="h-11 bg-card pl-10 text-base" /></div>
          <Button type="submit" className="h-11 px-6">Search</Button>
        </form>
        <div className="mt-6 flex flex-wrap justify-center gap-x-6 gap-y-3 text-sm">
          <Link href="/report?type=lost" className="text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline">I lost something</Link>
          <Link href="/report?type=found" className="inline-flex items-center gap-1.5 text-primary underline-offset-4 hover:underline">I found something <ArrowRight className="size-4" strokeWidth={1.5} /></Link>
        </div>
      </section>

      <section aria-label="Statistics" className="grid grid-cols-2 divide-x divide-y border-y sm:grid-cols-4 sm:divide-y-0">
        {[["Open lost reports", stats.data?.open_lost], ["Open found items", stats.data?.open_found], ["Items returned", stats.data?.returned],
          ["Recovery rate", stats.data?.recovery_rate_pct != null ? `${stats.data.recovery_rate_pct}%` : undefined]].map(([label, v]) => (
          <div key={label as string} className="px-5 py-7 sm:px-8 sm:py-9">
            <div className="tabular text-3xl font-light tracking-tight">{stats.loading ? "…" : v ?? "–"}</div>
            <div className="eyebrow mt-2">{label}</div>
          </div>))}
      </section>

      <section>
        <div className="mb-8 flex items-end justify-between gap-4"><h2 className="text-2xl font-light tracking-tight">Recently found</h2><Link href="/items?item_type=found" className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline">See all <ArrowRight className="size-4" strokeWidth={1.5} /></Link></div>
        {latest.loading ? <CardGridSkeleton n={4} /> : latest.error ? <ErrorState error={latest.error} retry={latest.reload} /> :
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{latest.data?.items.slice(0, 4).map((i) => <ItemCard key={i.item_id} item={i} />)}</div>}
      </section>

      <section>
        <h2 className="mb-8 text-2xl font-light tracking-tight">How it works</h2>
        <div className="grid gap-10 md:grid-cols-3 md:gap-8">
          {[[Camera, "01", "Report", "Describe the item, add photos, say where and when. It takes about a minute."],
            [Sparkles, "02", "We match", "Every report is compared with all open reports of the opposite kind. You see why each match was suggested."],
            [ShieldCheck, "03", "Verify and return", "Claim a found item with proof. Staff verify it, and the hand-over is recorded end to end."]].map(([Icon, n, t, d], i) => {
            const I = Icon as typeof BadgeCheck;
            return <div key={i} className="border-t pt-6"><div className="mb-5 flex items-center justify-between text-muted-foreground"><I className="size-5 text-primary" strokeWidth={1.5} /><span className="eyebrow tabular">{n as string}</span></div><h3 className="font-medium tracking-tight">{t as string}</h3><p className="mt-2 text-sm leading-relaxed text-muted-foreground">{d as string}</p></div>;
          })}
        </div>
      </section>
    </div>
  );
}
