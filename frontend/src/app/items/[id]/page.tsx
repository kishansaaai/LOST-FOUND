"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, CalendarDays, Check, ChevronDown, Info, Loader2, MapPin, Sparkles, Tag, User as UserIcon, X } from "lucide-react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ClaimDialog } from "@/components/claim-dialog";
import { ErrorState, EmptyState } from "@/components/states";
import { ItemThumb } from "@/components/item-card";
import { ScoreExplain } from "@/components/score-explain";
import { StatusBadge } from "@/components/status-badge";
import { useQuery } from "@/hooks/use-query";
import { ApiError, api, imgUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, titleCase } from "@/lib/format";
import { CATEGORY_LABEL, type ItemDetail, type ItemMatch } from "@/lib/types";
import { cn } from "@/lib/utils";

function Gallery({ urls, title }: { urls: string[]; title: string }) {
  const [i, setI] = useState(0);
  if (!urls.length) return <ItemThumb item={{ image_urls: [], title }} className="aspect-[4/3] w-full rounded-2xl" />;
  return (
    <div className="space-y-2">
      
      <img src={imgUrl(urls[i])} alt={title} className="aspect-[4/3] w-full rounded-2xl border bg-muted object-cover" />
      {urls.length > 1 && <div className="flex gap-2">{urls.map((u, n) => (
        <button key={u} onClick={() => setI(n)} aria-label={`Photo ${n + 1}`} aria-current={n === i} className={cn("size-16 overflow-hidden rounded-lg border-2", n === i ? "border-primary" : "border-transparent opacity-70")}>
          <img src={imgUrl(u)} alt="" className="size-full object-cover" /></button>))}</div>}
    </div>
  );
}

function MatchCard({ m, item, isStaff, onChange, onClaim }: { m: ItemMatch; item: ItemDetail; isStaff: boolean; onChange: () => void; onClaim: (matchId: number, otherId: number) => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  async function decide(kind: "confirm" | "reject") {
    setBusy(true);
    try { await api.post(`/staff/matches/${m.match_id}/${kind}`); toast.success(`Match ${kind === "confirm" ? "confirmed" : "rejected"}`); onChange(); }
    catch (e) { toast.error((e as Error).message); }
    setBusy(false);
  }
  const strength = Math.round(m.explanation.confidence * 100);
  return (
    <li className="rounded-xl border bg-card p-4">
      <div className="flex gap-4">
        <Link href={`/items/${m.other_item_id}`} className="shrink-0" aria-label={`View ${m.other_title}`}><ItemThumb item={{ image_urls: m.other_images, title: m.other_title }} className="size-20 rounded-lg" /></Link>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><Link href={`/items/${m.other_item_id}`} className="font-medium hover:underline">{m.other_title}</Link><StatusBadge value={m.other_type} /><StatusBadge value={m.status} /></div>
          <p className="mt-0.5 text-xs text-muted-foreground">{m.other_location} · {fmtDate(m.other_date)}</p>
          <div className="mt-2 flex items-center gap-2"><div className="h-1.5 w-28 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${strength}%` }} /></div><span className="tabular text-xs font-medium">{strength}% confidence</span></div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => setOpen(!open)} aria-expanded={open}><Info className="size-4" />Why this match?<ChevronDown className={cn("size-4 transition", open && "rotate-180")} /></Button>
        {item.is_mine && item.item_type === "lost" && m.other_type === "found" && ["open", "matched"].includes(m.other_status) && (
          <Button size="sm" onClick={() => onClaim(m.match_id, m.other_item_id)}>This is mine: claim it</Button>)}
        {isStaff && m.status === "suggested" && <>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => decide("confirm")}><Check className="size-4" />Confirm</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => decide("reject")}><X className="size-4" />Reject</Button></>}
      </div>
      {open && <div className="mt-3 border-t pt-3"><ScoreExplain e={m.explanation} /></div>}
    </li>
  );
}

function Detail() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const router = useRouter();
  const { user, isStaff } = useAuth();
  const item = useQuery(() => api.get<ItemDetail>(`/items/${id}`), [id, user?.id]);
  const canSeeMatches = !!item.data && (item.data.is_mine || isStaff);
  const matches = useQuery(() => api.get<{ matches: ItemMatch[] }>(`/items/${id}/matches`), [id, user?.id, canSeeMatches], canSeeMatches);
  const [claimOverride, setClaimOverride] = useState<boolean | null>(null);
  const [presetMatch, setPresetMatch] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const claimOpen = claimOverride ?? (!!sp.get("claim") && !!item.data?.claimable);   // ?claim=<match> opens the dialog
  const setClaimOpen = setClaimOverride;

  if (item.loading && !item.data) return <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]"><Skeleton className="aspect-[4/3] w-full rounded-2xl" /><div className="space-y-3"><Skeleton className="h-8 w-2/3" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /></div></div>;
  if (item.error) return (item.error as ApiError).status === 404 ? <EmptyState title="Item not found" hint="It may have been removed." action={<Link className={buttonVariants()} href="/items">Browse items</Link>} /> : <ErrorState error={item.error} retry={item.reload} />;
  const it = item.data!;

  async function act(key: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(key);
    try { await fn(); toast.success(ok); item.reload(); matches.reload(); } catch (e) { toast.error((e as Error).message); }
    setBusy(null);
  }

  const facts: [React.ReactNode, string][] = [
    [<MapPin key="m" className="size-4" />, it.location_name], [<CalendarDays key="c" className="size-4" />, `${it.item_type === "lost" ? "Lost" : "Found"} on ${fmtDate(it.date_lost_or_found)}`],
    [<Tag key="t" className="size-4" />, [CATEGORY_LABEL[it.category], it.color, it.brand].filter(Boolean).join(" · ")], [<UserIcon key="u" className="size-4" />, `Reported by ${it.reporter_name}${it.is_mine ? " (you)" : ""}`],
  ];

  return (
    <div>
      <Link href="/items" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />All items</Link>
      <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
        <Gallery urls={it.image_urls} title={it.title} />
        <div className="space-y-5">
          <div><div className="mb-2 flex flex-wrap gap-2"><StatusBadge value={it.item_type} /><StatusBadge value={it.status} /></div>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{it.title}</h1></div>
          <p className="whitespace-pre-line text-muted-foreground">{it.description}</p>
          <ul className="space-y-2 text-sm">{facts.map(([icon, t], i) => t && <li key={i} className="flex items-center gap-2 text-muted-foreground"><span className="text-foreground">{icon}</span>{t}</li>)}</ul>
          {Object.keys(it.extras ?? {}).length > 0 && <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-xl bg-muted/60 p-3 text-sm">{Object.entries(it.extras).filter(([, v]) => v !== null && v !== "").map(([k, v]) => <div key={k} className="contents"><dt className="text-muted-foreground">{titleCase(k)}</dt><dd className="font-medium">{typeof v === "boolean" ? (v ? "Yes" : "No") : String(v)}</dd></div>)}</dl>}

          {it.my_claim && (
            <div className="rounded-xl border bg-accent/50 p-4 text-sm"><div className="mb-1 font-medium">Your claim</div>
              <div className="flex items-center gap-2"><StatusBadge value={it.my_claim.verification_status} /> <span className="text-muted-foreground">submitted {fmtDate(it.my_claim.submitted_at)}</span></div>
              <Link href="/claims" className="mt-2 inline-block text-primary hover:underline">Track your claims</Link></div>)}

          <div className="flex flex-wrap gap-2 border-t pt-4">
            {!user && it.item_type === "found" && it.status === "open" && <Link className={buttonVariants()} href={`/login?next=/items/${it.item_id}`}>Sign in to claim</Link>}
            {it.claimable && !it.my_claim && <Button onClick={() => { setPresetMatch(null); setClaimOpen(true); }}>Claim this item</Button>}
            {it.is_mine && it.status === "open" && <Button variant="outline" disabled={busy === "find"} onClick={() => act("find", () => api.post(`/items/${it.item_id}/find-matches`), "Matching finished")}>{busy === "find" ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}Find matches</Button>}
            {it.is_mine && ["open", "matched"].includes(it.status) && <Button variant="ghost" disabled={busy === "close"} onClick={() => { if (confirm("Close this report? Pending claims will be declined.")) act("close", () => api.post(`/items/${it.item_id}/close`), "Report closed"); }}>Close report</Button>}
            {isStaff && it.item_type === "found" && it.status === "claimed" && <Button disabled={busy === "ret"} onClick={() => act("ret", () => api.post(`/staff/items/${it.item_id}/mark-returned`), "Marked as returned")}><Check className="size-4" />Mark returned</Button>}
            {isStaff && (it.claim_count ?? 0) > 0 && <Link className={buttonVariants({ variant: "outline" })} href="/staff/claims">{it.claim_count} claim{it.claim_count === 1 ? "" : "s"} in queue</Link>}
          </div>
        </div>
      </div>

      {canSeeMatches && (
        <section className="mt-12" aria-labelledby="matches-h">
          <h2 id="matches-h" className="mb-1 text-xl font-semibold tracking-tight">Suggested matches</h2>
          <p className="mb-4 text-sm text-muted-foreground">Ranked by Reciprocal Rank Fusion of text and photo similarity. Only you and staff can see this.</p>
          {matches.loading && !matches.data ? <Skeleton className="h-28 w-full rounded-xl" /> : matches.error ? <ErrorState error={matches.error} retry={matches.reload} />
            : !matches.data?.matches.length ? <EmptyState title="No matches yet" hint={it.status === "open" ? "New reports are compared as they arrive. We will notify you when something lines up." : "This report is no longer being matched."} />
              : <ul className="space-y-3">{matches.data.matches.map((m) => <MatchCard key={m.match_id} m={m} item={it} isStaff={isStaff} onChange={() => { matches.reload(); item.reload(); }}
                onClaim={(mid, other) => router.push(`/items/${other}?claim=${mid}`)} />)}</ul>}
        </section>)}

      <ClaimDialog itemId={it.item_id} itemTitle={it.title} open={claimOpen} onOpenChange={setClaimOpen} presetMatch={presetMatch ?? sp.get("claim")} onDone={() => item.reload()} />
    </div>
  );
}

export default function Page() { return <Suspense><Detail /></Suspense>; }
