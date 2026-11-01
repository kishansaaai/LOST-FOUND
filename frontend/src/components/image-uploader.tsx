"use client";
import { useRef, useState } from "react";
import { ImagePlus, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, imgUrl } from "@/lib/api";

export function ImageUploader({ value, onChange, max = 3 }: { value: string[]; onChange: (v: string[]) => void; max?: number }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function pick(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    const next = [...value];
    for (const f of Array.from(files).slice(0, max - value.length)) {
      if (!f.type.startsWith("image/")) { toast.error(`${f.name} is not an image`); continue; }
      if (f.size > 8 * 1024 * 1024) { toast.error(`${f.name} is larger than 8 MB`); continue; }
      try { next.push((await api.upload<{ url: string }>("/uploads", f)).url); }
      catch (e) { toast.error((e as Error).message); }
    }
    onChange(next);
    setBusy(false);
    if (input.current) input.current.value = "";
  }

  return (
    <div className="flex flex-wrap gap-3">
      {value.map((u) => (
        <div key={u} className="relative size-24 overflow-hidden rounded-lg border">
          
          <img src={imgUrl(u)} alt="Uploaded" className="size-full object-cover" />
          <button type="button" aria-label="Remove photo" onClick={() => onChange(value.filter((x) => x !== u))}
            className="absolute right-1 top-1 rounded-full bg-background/90 p-1 shadow hover:bg-background"><X className="size-3" /></button>
        </div>
      ))}
      {value.length < max && (
        <Button type="button" variant="outline" disabled={busy} onClick={() => input.current?.click()} className="size-24 flex-col gap-1 border-dashed">
          {busy ? <Loader2 className="size-5 animate-spin" /> : <ImagePlus className="size-5" />}
          <span className="text-xs">{busy ? "Uploading" : "Add photo"}</span>
        </Button>
      )}
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple hidden onChange={(e) => pick(e.target.files)} />
    </div>
  );
}
