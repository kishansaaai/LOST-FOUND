"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { HandHeart, Loader2, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ImageUploader } from "@/components/image-uploader";
import { PageHeader } from "@/components/states";
import { SimpleSelect } from "@/components/simple-select";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { CATEGORIES, CATEGORY_LABEL, type ItemType, type Location } from "@/lib/types";
import { cn } from "@/lib/utils";

type Field = { key: string; label: string; kind: "text" | "number" | "bool" };
const EXTRA_FIELDS: Record<string, Field[]> = {
  electronics: [{ key: "serial_number", label: "Serial number", kind: "text" }, { key: "imei_last4", label: "IMEI (last 4 digits)", kind: "text" }],
  id_card: [{ key: "card_type", label: "Card type", kind: "text" }, { key: "name_visible", label: "Name is visible on the card", kind: "bool" }],
  pet: [{ key: "breed", label: "Breed", kind: "text" }, { key: "microchipped", label: "Microchipped", kind: "bool" }],
  keys: [{ key: "key_count", label: "Number of keys", kind: "number" }, { key: "has_fob", label: "Has a key fob", kind: "bool" }],
  wallet_bag: [{ key: "contains_cards", label: "Contains cards", kind: "bool" }, { key: "contains_cash", label: "Contains cash", kind: "bool" }],
};
const today = () => new Date().toISOString().slice(0, 10);

function ReportForm() {
  const { allowed } = useRequireAuth();
  const router = useRouter();
  const [type, setType] = useState<ItemType>(useSearchParams().get("type") === "found" ? "found" : "lost");
  const [f, setF] = useState({ title: "", description: "", category: "", location_id: "", date: today(), color: "", brand: "" });
  const [images, setImages] = useState<string[]>([]);
  const [extras, setExtras] = useState<Record<string, string | boolean>>({});
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const locations = useQuery(() => api.get<Location[]>("/locations"), []);
  const upd = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const isLost = type === "lost";

  function validate() {
    const e: Record<string, string> = {};
    if (f.title.trim().length < 3) e.title = "Give it a short title (at least 3 characters).";
    if (f.description.trim().length < 10) e.description = "Describe it in a sentence or two: distinguishing marks help most.";
    if (!f.category) e.category = "Choose a category.";
    if (!f.location_id) e.location_id = "Choose where it happened.";
    if (!f.date || f.date > today()) e.date = "Pick a date that is not in the future.";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!validate()) return;
    setBusy(true);
    try {
      const clean: Record<string, string | boolean | number> = Object.fromEntries(Object.entries(extras).filter(([, v]) => v !== "" && v !== undefined));
      for (const fld of EXTRA_FIELDS[f.category] ?? []) if (fld.kind === "number" && clean[fld.key] !== undefined) clean[fld.key] = Number(clean[fld.key]);
      const r = await api.post<{ item_id: number }>("/items", {
        item_type: type, title: f.title.trim(), description: f.description.trim(), category: f.category,
        location_id: Number(f.location_id), date_lost_or_found: f.date, color: f.color || null, brand: f.brand || null,
        image_urls: images, extras: clean,
      });
      toast.success("Reported. We are checking it against open reports now.");
      router.push(`/items/${r.item_id}`);
    } catch (e) { toast.error((e as Error).message); setBusy(false); }
  }

  if (!allowed) return null;
  const err = (k: string) => errors[k] && <p role="alert" className="text-xs text-destructive">{errors[k]}</p>;

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Report an item" description="The more precise the description, the better the matches." />
      <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Report type">
        {([["lost", "I lost something", Search], ["found", "I found something", HandHeart]] as const).map(([v, label, Icon]) => (
          <button key={v} type="button" role="radio" aria-checked={type === v} onClick={() => setType(v)}
            className={cn("flex items-center gap-3 rounded-lg border p-4 text-left transition", type === v ? "border-primary bg-primary/5 ring-2 ring-primary/30" : "hover:bg-muted")}>
            <span className="grid size-9 place-items-center rounded-lg bg-primary/10 text-primary"><Icon className="size-5" /></span><span className="font-medium">{label}</span>
          </button>))}
      </div>
      <Card><CardContent className="pt-6">
        <form onSubmit={submit} className="space-y-5" noValidate>
          <div className="space-y-1.5"><Label htmlFor="title">Title</Label><Input id="title" value={f.title} onChange={upd("title")} placeholder={isLost ? "Black leather wallet" : "Wallet found near the library desk"} maxLength={200} aria-invalid={!!errors.title} />{err("title")}</div>
          <div className="space-y-1.5"><Label htmlFor="description">Description</Label><Textarea id="description" rows={4} value={f.description} onChange={upd("description")} placeholder="Colour, brand, marks, stickers, what was inside…" maxLength={5000} aria-invalid={!!errors.description} />{err("description")}
            {!isLost && <p className="text-xs text-muted-foreground">Tip: leave out one detail only the owner would know. Staff will ask for it when verifying a claim.</p>}</div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5"><Label htmlFor="category">Category</Label><SimpleSelect id="category" value={f.category} onChange={(v) => { setF({ ...f, category: v }); setExtras({}); }} placeholder="Choose…" options={CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABEL[c] }))} />{err("category")}</div>
            <div className="space-y-1.5"><Label htmlFor="location">{isLost ? "Where did you lose it?" : "Where did you find it?"}</Label><SimpleSelect id="location" value={f.location_id} onChange={(v) => setF({ ...f, location_id: v })} placeholder="Choose…" options={(locations.data ?? []).map((l) => ({ value: String(l.location_id), label: l.location_name }))} />{err("location_id")}</div>
            <div className="space-y-1.5"><Label htmlFor="date">{isLost ? "Date lost" : "Date found"}</Label><Input id="date" type="date" max={today()} value={f.date} onChange={upd("date")} aria-invalid={!!errors.date} />{err("date")}</div>
            <div className="space-y-1.5"><Label htmlFor="color">Colour <span className="text-muted-foreground">(optional)</span></Label><Input id="color" value={f.color} onChange={upd("color")} placeholder="black" maxLength={60} /></div>
            <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="brand">Brand <span className="text-muted-foreground">(optional)</span></Label><Input id="brand" value={f.brand} onChange={upd("brand")} placeholder="Fossil, JanSport, Samsung…" maxLength={80} /></div>
          </div>
          {(EXTRA_FIELDS[f.category] ?? []).length > 0 && (
            <fieldset className="space-y-3 rounded-lg bg-muted/50 p-4"><legend className="px-1 text-sm font-medium">{CATEGORY_LABEL[f.category]} details <span className="font-normal text-muted-foreground">(optional)</span></legend>
              <div className="grid gap-3 sm:grid-cols-2">
                {EXTRA_FIELDS[f.category].map((fld) => fld.kind === "bool" ? (
                  <label key={fld.key} className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={!!extras[fld.key]} onChange={(e) => setExtras({ ...extras, [fld.key]: e.target.checked })} />{fld.label}</label>
                ) : (
                  <div key={fld.key} className="space-y-1"><Label htmlFor={fld.key} className="text-xs">{fld.label}</Label><Input id={fld.key} type={fld.kind === "number" ? "number" : "text"} min={0} value={String(extras[fld.key] ?? "")} onChange={(e) => setExtras({ ...extras, [fld.key]: e.target.value })} /></div>))}
              </div></fieldset>)}
          <div className="space-y-2"><Label>Photos <span className="text-muted-foreground">(optional, up to 3, photos improve matching)</span></Label><ImageUploader value={images} onChange={setImages} /></div>
          <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy && <Loader2 className="size-4 animate-spin" />}Submit {type} report</Button>
        </form>
      </CardContent></Card>
    </div>
  );
}

export default function Page() { return <Suspense><ReportForm /></Suspense>; }
