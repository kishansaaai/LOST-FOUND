"use client";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Camera, ChevronLeft, ChevronRight, Loader2, Search, SlidersHorizontal, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CardGridSkeleton, EmptyState, ErrorState, PageHeader } from "@/components/states";
import { ItemCard } from "@/components/item-card";
import { SimpleSelect } from "@/components/simple-select";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { CATEGORIES, CATEGORY_LABEL, type Item, type Location } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Page { items: Item[]; total: number; page: number; page_size: number }
const ALL = "all";

function Browse() {
  const sp = useSearchParams();
  const router = useRouter();
  const get = (k: string, d = "") => sp.get(k) ?? d;
  const [q, setQ] = useState(get("q"));
  const [imageResults, setImageResults] = useState<Item[] | null>(null);
  const [searching, setSearching] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const set = (patch: Record<string, string | null>) => {
    const p = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "" || v === ALL) p.delete(k);
      else p.set(k, v);
    }
    if (!("page" in patch)) p.delete("page");
    router.replace(`/items?${p.toString()}`, { scroll: false });
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setTimeout(() => { if (q !== get("q")) set({ q }); }, 350); return () => clearTimeout(t); }, [q]);

  const qs = useMemo(() => {
    const p = new URLSearchParams();
    for (const k of ["q", "item_type", "category", "location_id", "status", "date_from", "date_to", "page"]) if (sp.get(k)) p.set(k, sp.get(k)!);
    p.set("page_size", "12");
    return p.toString();
  }, [sp]);

  const locations = useQuery(() => api.get<Location[]>("/locations"), []);
  const res = useQuery(() => api.get<Page>(`/items?${qs}`), [qs], imageResults === null);
  const pages = res.data ? Math.max(1, Math.ceil(res.data.total / res.data.page_size)) : 1;
  const page = Number(get("page", "1"));
  const activeFilters = ["item_type", "category", "location_id", "status", "date_from", "date_to"].filter((k) => sp.get(k) && sp.get(k) !== "open" || (k === "status" && sp.get(k) && sp.get(k) !== "open"));

  async function imageSearch(file: File | undefined) {
    if (!file) return;
    setSearching(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await api.upload<{ items: Item[] }>(`/search/by-image${get("item_type") ? `?item_type=${get("item_type")}` : ""}`, file);
      setImageResults(r.items);
      if (!r.items.length) toast.info("No visually similar items yet.");
    } catch (e) { toast.error((e as Error).message); }
    setSearching(false);
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div>
      <PageHeader title="Browse items" description="Search by keyword, filter by what matters, or look up an item by photo." />
      <div className="mb-8 space-y-4 rounded-lg border bg-card p-5 sm:p-6">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input aria-label="Search" value={q} onChange={(e) => setQ(e.target.value)} placeholder='Try "black leather wallet" or keys OR lanyard' className="h-9 pl-9" /></div>
          <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => imageSearch(e.target.files?.[0])} />
          <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={searching}>{searching ? <Loader2 className="size-4 animate-spin" /> : <Camera className="size-4" />}Search by photo</Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SlidersHorizontal className="size-4 text-muted-foreground" aria-hidden />
          <div role="group" aria-label="Type" className="inline-flex rounded-lg border p-0.5">
            {[[ALL, "All"], ["lost", "Lost"], ["found", "Found"]].map(([v, l]) => {
              const on = (get("item_type") || ALL) === v;
              return <button key={v} type="button" aria-pressed={on} onClick={() => set({ item_type: v })} className={cn("rounded-md px-3 py-1.5 text-sm transition", on ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>{l}</button>;
            })}
          </div>
          <SimpleSelect size="sm" className="w-44" value={get("category") || ALL} onChange={(v) => set({ category: v })} options={[{ value: ALL, label: "All categories" }, ...CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABEL[c] }))]} />
          <SimpleSelect size="sm" className="w-56" value={get("location_id") || ALL} onChange={(v) => set({ location_id: v })} options={[{ value: ALL, label: "Any location" }, ...(locations.data ?? []).map((l) => ({ value: String(l.location_id), label: l.location_name }))]} />
          <SimpleSelect size="sm" className="w-36" value={get("status", "open")} onChange={(v) => set({ status: v })} options={[{ value: "open", label: "Open" }, { value: "matched", label: "Matched" }, { value: "claimed", label: "Claimed" }, { value: "returned", label: "Returned" }, { value: "closed", label: "Closed" }, { value: "any", label: "Any status" }]} />
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground">From<Input type="date" aria-label="From date" value={get("date_from")} onChange={(e) => set({ date_from: e.target.value })} className="h-7 w-36" /></label>
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground">To<Input type="date" aria-label="To date" value={get("date_to")} onChange={(e) => set({ date_to: e.target.value })} className="h-7 w-36" /></label>
          {(activeFilters.length > 0 || get("q")) && <Button variant="ghost" size="sm" onClick={() => { setQ(""); router.replace("/items"); }}><X className="size-3.5" />Clear</Button>}
        </div>
      </div>

      {imageResults !== null ? (
        <div>
          <div className="mb-3 flex items-center justify-between rounded-lg bg-accent px-4 py-2 text-sm"><span>Showing items that look like your photo</span><Button size="xs" variant="ghost" onClick={() => setImageResults(null)}>Back to all items</Button></div>
          <h2 className="sr-only">Visually similar items</h2>
          {imageResults.length ? <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{imageResults.map((i) => <ItemCard key={i.item_id} item={i} />)}</div>
            : <EmptyState title="No similar photos" hint="Only reports that include a photo can be matched by image." />}
        </div>
      ) : res.loading ? <CardGridSkeleton /> : res.error ? <ErrorState error={res.error} retry={res.reload} /> : !res.data?.items.length ? (
        <EmptyState title="Nothing matches those filters" hint="Try fewer filters, a different keyword, or report the item so we can watch for it." />
      ) : (
        <>
          <h2 className="sr-only">Results</h2>
          <p className="mb-3 text-sm text-muted-foreground" aria-live="polite">{res.data.total} item{res.data.total === 1 ? "" : "s"}</p>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{res.data.items.map((i) => <ItemCard key={i.item_id} item={i} />)}</div>
          {pages > 1 && (
            <nav className="mt-8 flex items-center justify-center gap-3" aria-label="Pagination">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}><ChevronLeft className="size-4" />Previous</Button>
              <span className="tabular text-sm text-muted-foreground">Page {page} of {pages}</span>
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => set({ page: String(page + 1) })}>Next<ChevronRight className="size-4" /></Button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

export default function Page() { return <Suspense><Browse /></Suspense>; }
