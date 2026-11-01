"use client";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ImageUploader } from "@/components/image-uploader";
import { SimpleSelect } from "@/components/simple-select";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";

interface Linkable { match_id: number; lost_item_id: number; lost_title: string; rrf_score: number }

export function ClaimDialog({ itemId, itemTitle, open, onOpenChange, presetMatch, onDone }: {
  itemId: number; itemTitle: string; open: boolean; onOpenChange: (o: boolean) => void; presetMatch?: string | null; onDone: () => void;
}) {
  const [proof, setProof] = useState("");
  const [img, setImg] = useState<string[]>([]);
  const [match, setMatch] = useState<string>(presetMatch ?? "none");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const linkable = useQuery(() => api.get<{ matches: Linkable[] }>(`/items/${itemId}/claimable-matches`), [itemId], open);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (proof.trim().length < 10) return setError("Describe how you know it is yours (at least 10 characters).");
    setBusy(true); setError("");
    try {
      await api.post(`/items/${itemId}/claims`, { proof_description: proof.trim(), proof_image_url: img[0] ?? null, match_id: match !== "none" ? Number(match) : null });
      toast.success("Claim submitted. Staff will review your proof.");
      onOpenChange(false); onDone();
    } catch (err) { setError((err as Error).message); }
    setBusy(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader><DialogTitle>Claim “{itemTitle}”</DialogTitle>
            <DialogDescription>Staff compare your proof with the item before anything is handed over. Share something only the owner would know.</DialogDescription></DialogHeader>
          <div className="space-y-1.5"><Label htmlFor="proof">Proof of ownership</Label>
            <Textarea id="proof" rows={4} value={proof} onChange={(e) => setProof(e.target.value)} placeholder="What was inside, serial number, marks, when and where you lost it…" maxLength={3000} /></div>
          <div className="space-y-1.5"><Label>Photo proof <span className="text-muted-foreground">(receipt, earlier photo; optional)</span></Label><ImageUploader value={img} onChange={setImg} max={1} /></div>
          {!!linkable.data?.matches.length && (
            <div className="space-y-1.5"><Label htmlFor="match">Link to your lost report</Label>
              <SimpleSelect id="match" value={match} onChange={setMatch} options={[{ value: "none", label: "Not linked" }, ...linkable.data.matches.map((m) => ({ value: String(m.match_id), label: `${m.lost_title} (#${m.lost_item_id})` }))]} /></div>)}
          {error && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          <DialogFooter><Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={busy}>{busy && <Loader2 className="size-4 animate-spin" />}Submit claim</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
