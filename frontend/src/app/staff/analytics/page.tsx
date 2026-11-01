"use client";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ErrorState, ListSkeleton, PageHeader } from "@/components/states";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { CATEGORY_LABEL } from "@/lib/types";
import { titleCase } from "@/lib/format";

interface Summary {
  status_counts: { item_type: string; status: string; n: number }[];
  recovery: { category: string; found_items: number; returned_items: number; recovery_rate_pct: number | null; avg_hours_to_return: number | null; median_hours_to_return: number | null }[];
  hotspots: { location_name: string; lost_count: number; found_count: number; total_items: number; hotspot_rank: number }[];
  match_quality: { score_bucket: number; matches: number; confirmed: number; rejected: number; confirm_rate_pct: number | null; avg_text_score: number | null; avg_image_score: number | null }[];
  queue: { pending_claims: number };
}
const STATUSES = ["open", "matched", "claimed", "returned", "closed"];
const STATUS_COLOR: Record<string, string> = { open: "bg-sky-500", matched: "bg-violet-500", claimed: "bg-indigo-500", returned: "bg-emerald-500", closed: "bg-zinc-400" };

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return <div className="rounded-xl border bg-card p-4"><div className="tabular text-2xl font-semibold">{value}</div><div className="text-sm text-muted-foreground">{label}</div>{hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}</div>;
}
const hours = (h: number | null) => (h == null ? "–" : h >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(0)} h`);

export default function Analytics() {
  const q = useQuery(() => api.get<Summary>("/analytics/summary"), []);
  async function refresh() { try { await api.post("/analytics/refresh"); q.reload(); toast.success("Materialized views refreshed"); } catch (e) { toast.error((e as Error).message); } }
  if (q.loading && !q.data) return <ListSkeleton n={5} />;
  if (q.error) return <ErrorState error={q.error} retry={q.reload} />;
  const s = q.data!;
  const all = s.recovery.find((r) => r.category === "ALL");
  const byType = (t: string) => STATUSES.map((st) => ({ st, n: s.status_counts.find((c) => c.item_type === t && c.status === st)?.n ?? 0 }));
  const maxHot = Math.max(1, ...s.hotspots.map((h) => h.total_items));
  const cats = s.recovery.filter((r) => r.category !== "ALL");
  const maxBucket = Math.max(1, ...s.match_quality.map((b) => b.matches));

  return (
    <div className="space-y-8">
      <PageHeader title="Analytics" description="Served from materialized views; they refresh every few minutes without blocking readers." actions={<Button variant="outline" size="sm" onClick={refresh}><RefreshCw className="size-4" />Refresh now</Button>} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Recovery rate" value={all?.recovery_rate_pct != null ? `${all.recovery_rate_pct}%` : "–"} hint={`${all?.returned_items ?? 0} of ${all?.found_items ?? 0} found items returned`} />
        <Stat label="Avg. time to return" value={hours(all?.avg_hours_to_return ?? null)} hint={`median ${hours(all?.median_hours_to_return ?? null)}`} />
        <Stat label="Claims waiting" value={s.queue.pending_claims} />
        <Stat label="Open reports" value={s.status_counts.filter((c) => c.status === "open").reduce((a, c) => a + c.n, 0)} />
      </div>

      <section aria-labelledby="st"><h2 id="st" className="mb-3 text-lg font-semibold">Items by status</h2>
        <div className="space-y-3 rounded-xl border bg-card p-4">
          {["lost", "found"].map((t) => { const rows_ = byType(t); const total = rows_.reduce((a, r) => a + r.n, 0) || 1; return (
            <div key={t}><div className="mb-1 flex justify-between text-sm"><span className="font-medium capitalize">{t}</span><span className="tabular text-muted-foreground">{total === 1 && !rows_.some((r) => r.n) ? 0 : total}</span></div>
              <div className="flex h-5 overflow-hidden rounded-md bg-muted" role="img" aria-label={`${t}: ${rows_.map((r) => `${r.n} ${r.st}`).join(", ")}`}>{rows_.map((r) => r.n > 0 && <div key={r.st} className={STATUS_COLOR[r.st]} style={{ width: `${(r.n / total) * 100}%` }} title={`${r.st}: ${r.n}`} />)}</div></div>); })}
          <ul className="flex flex-wrap gap-4 pt-1 text-xs text-muted-foreground">{STATUSES.map((st) => <li key={st} className="flex items-center gap-1.5"><span className={`size-2.5 rounded-sm ${STATUS_COLOR[st]}`} />{titleCase(st)}</li>)}</ul>
        </div></section>

      <div className="grid gap-8 lg:grid-cols-2">
        <section aria-labelledby="rc"><h2 id="rc" className="mb-3 text-lg font-semibold">Recovery by category</h2>
          <ul className="space-y-2 rounded-xl border bg-card p-4">{cats.map((c) => (
            <li key={c.category}><div className="mb-1 flex justify-between text-sm"><span>{CATEGORY_LABEL[c.category] ?? c.category}</span><span className="tabular text-muted-foreground">{c.recovery_rate_pct ?? 0}% · {c.returned_items}/{c.found_items} · {hours(c.avg_hours_to_return)}</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${c.recovery_rate_pct ?? 0}%` }} /></div></li>))}</ul></section>

        <section aria-labelledby="hs"><h2 id="hs" className="mb-3 text-lg font-semibold">Hot-spot locations</h2>
          <ul className="space-y-2 rounded-xl border bg-card p-4">{s.hotspots.map((h) => (
            <li key={h.location_name}><div className="mb-1 flex justify-between text-sm"><span><span className="tabular mr-2 text-muted-foreground">#{h.hotspot_rank}</span>{h.location_name}</span><span className="tabular text-muted-foreground">{h.lost_count} lost · {h.found_count} found</span></div>
              <div className="flex h-2 overflow-hidden rounded-full bg-muted" style={{ width: `${(h.total_items / maxHot) * 100}%` }}><div className="bg-amber-500" style={{ width: `${(h.lost_count / h.total_items) * 100}%` }} /><div className="flex-1 bg-emerald-500" /></div></li>))}</ul></section>
      </div>

      <section aria-labelledby="mq"><h2 id="mq" className="mb-1 text-lg font-semibold">Match quality</h2>
        <p className="mb-3 text-sm text-muted-foreground">Do higher RRF scores get confirmed more often by staff? Buckets are slices of the score range (1 = weakest).</p>
        <div className="overflow-x-auto rounded-xl border"><table className="w-full text-left text-sm"><thead className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground"><tr>{["Score bucket", "Matches", "Confirmed", "Rejected", "Confirm rate", "Avg text", "Avg image"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody>{s.match_quality.map((b) => <tr key={b.score_bucket} className="border-t"><td className="tabular px-3 py-2">{b.score_bucket}</td><td className="px-3 py-2"><div className="flex items-center gap-2"><span className="tabular w-8">{b.matches}</span><div className="h-2 rounded-full bg-primary/70" style={{ width: `${(b.matches / maxBucket) * 80}px` }} /></div></td>
            <td className="tabular px-3 py-2">{b.confirmed}</td><td className="tabular px-3 py-2">{b.rejected}</td><td className="tabular px-3 py-2">{b.confirm_rate_pct != null ? `${b.confirm_rate_pct}%` : "–"}</td><td className="tabular px-3 py-2">{b.avg_text_score ?? "–"}</td><td className="tabular px-3 py-2">{b.avg_image_score ?? "–"}</td></tr>)}</tbody></table></div></section>
    </div>
  );
}
