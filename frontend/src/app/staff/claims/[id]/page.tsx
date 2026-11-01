"use client";
import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Check, Loader2, PlayCircle, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorState, ListSkeleton } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { useQuery } from "@/hooks/use-query";
import { api, imgUrl } from "@/lib/api";
import { fmtDate, pct, timeAgo } from "@/lib/format";


interface Review {
  claim: { claim_id: number; item_id: number; claimant_name: string; claimant_email: string; claimant_phone: string | null; proof_description: string;
    proof_image_url: string | null; verification_status: string; result: string; submitted_at: string; notes: string | null; reviewed_at: string | null; match_id: number | null };
  item: { item_id: number; title: string; description: string; category: string; color: string | null; brand: string | null; image_urls: string[]; status: string; date_lost_or_found: string; location_name: string };
  match: { rrf_score: number; text_score: number | null; image_score: number | null; lost_title: string } | null;
  other_claims: { claim_id: number; claimant_id: number; verification_status: string; result: string; submitted_at: string }[];
}

export default function ClaimReview() {
  const { id } = useParams<{ id: string }>();
  const q = useQuery(() => api.get<Review>(`/staff/claims/${id}`), [id]);
  const [dlg, setDlg] = useState<"approve" | "reject" | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(path: string, body?: object, ok?: string) {
    setBusy(true);
    try { await api.post(`/staff/claims/${id}/${path}`, body); if (ok) toast.success(ok); setDlg(null); setNotes(""); q.reload(); }
    catch (e) { toast.error((e as Error).message); }
    setBusy(false);
  }
  if (q.loading && !q.data) return <ListSkeleton n={2} />;
  if (q.error) return <ErrorState error={q.error} retry={q.reload} />;
  const { claim, item, match, other_claims } = q.data!;
  const decided = claim.result !== "pending";

  return (
    <div>
      <Link href="/staff/claims" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />Queue</Link>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Claim #{claim.claim_id} <span className="ml-2 align-middle"><StatusBadge value={decided ? claim.result : claim.verification_status} /></span></h1>
        {!decided && <div className="flex gap-2">
          {claim.verification_status === "pending" && <Button variant="outline" disabled={busy} onClick={() => run("start-review", undefined, "Review started")}><PlayCircle className="size-4" />Start review</Button>}
          <Button variant="outline" onClick={() => setDlg("reject")}><X className="size-4" />Reject</Button>
          <Button onClick={() => setDlg("approve")}><Check className="size-4" />Approve</Button></div>}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3 rounded-2xl border bg-card p-5" aria-label="Found item">
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">The found item</h2>
          {item.image_urls[0] ? <img src={imgUrl(item.image_urls[0])} alt={item.title} className="aspect-[4/3] w-full rounded-xl border object-cover" /> : <div className="grid aspect-[4/3] place-items-center rounded-xl bg-muted text-sm text-muted-foreground">No photo</div>}
          <Link href={`/items/${item.item_id}`} className="text-lg font-medium hover:underline">{item.title}</Link>
          <p className="whitespace-pre-line text-sm text-muted-foreground">{item.description}</p>
          <p className="text-xs text-muted-foreground">{item.location_name} · found {fmtDate(item.date_lost_or_found)} · {[item.color, item.brand].filter(Boolean).join(", ")}</p>
        </section>
        <section className="space-y-3 rounded-2xl border bg-card p-5" aria-label="Claim">
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">The claim</h2>
          <div className="rounded-lg bg-muted/60 p-3 text-sm"><div className="font-medium">{claim.claimant_name}</div><div className="text-muted-foreground">{claim.claimant_email}{claim.claimant_phone && ` · ${claim.claimant_phone}`}</div><div className="mt-1 text-xs text-muted-foreground">Submitted {timeAgo(claim.submitted_at)}</div></div>
          <div><Label className="mb-1 block text-xs text-muted-foreground">Proof description</Label><p className="whitespace-pre-line rounded-lg border p-3 text-sm">{claim.proof_description}</p></div>
          {claim.proof_image_url && <div><Label className="mb-1 block text-xs text-muted-foreground">Proof photo</Label><img src={imgUrl(claim.proof_image_url)} alt="Proof" className="max-h-64 rounded-lg border" /></div>}
          {match && <div className="rounded-lg bg-accent/60 p-3 text-sm"><div className="font-medium">Linked to the claimant&apos;s lost report “{match.lost_title}”</div>
            <div className="text-muted-foreground">RRF {match.rrf_score.toFixed(4)} · text {pct(match.text_score)} · image {pct(match.image_score)}</div></div>}
          {other_claims.length > 0 && <div className="rounded-lg border border-amber-300/60 bg-amber-50 p-3 text-sm dark:bg-amber-500/10"><div className="font-medium">{other_claims.length} other claim{other_claims.length === 1 ? "" : "s"} on this item</div>
            <p className="text-muted-foreground">Approving this claim will automatically decline the other pending ones.</p></div>}
          {claim.notes && <p className="rounded-lg bg-muted px-3 py-2 text-sm"><span className="font-medium">Notes: </span>{claim.notes}</p>}
        </section>
      </div>

      <Dialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent><DialogHeader><DialogTitle>{dlg === "approve" ? "Approve this claim?" : "Reject this claim?"}</DialogTitle>
          <DialogDescription>{dlg === "approve" ? "The item becomes claimed and competing claims are declined automatically. This is recorded in the audit log." : "The claimant is notified. Add a note explaining the decision."}</DialogDescription></DialogHeader>
          <div className="space-y-1.5"><Label htmlFor="notes">Notes {dlg === "reject" ? "(required)" : "(optional)"}</Label><Textarea id="notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
          <DialogFooter><Button variant="ghost" onClick={() => setDlg(null)}>Cancel</Button>
            <Button disabled={busy || (dlg === "reject" && notes.trim().length < 3)} onClick={() => run(dlg!, { notes: notes.trim() || null }, dlg === "approve" ? "Claim approved" : "Claim rejected")}>{busy && <Loader2 className="size-4 animate-spin" />}{dlg === "approve" ? "Approve" : "Reject"}</Button></DialogFooter></DialogContent>
      </Dialog>
    </div>
  );
}
