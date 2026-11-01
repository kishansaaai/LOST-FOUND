import Link from "next/link";
import { CalendarDays, ImageOff, MapPin, Sparkles } from "lucide-react";
import { imgUrl } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { CATEGORY_LABEL, type Item } from "@/lib/types";
import { StatusBadge } from "./status-badge";

export function ItemThumb({ item, className = "" }: { item: Pick<Item, "image_urls" | "title">; className?: string }) {
  const src = imgUrl(item.image_urls?.[0]);
  return src ? (
    <img src={src} alt={item.title} loading="lazy" className={`object-cover ${className}`} />
  ) : (
    <div className={`flex items-center justify-center bg-muted text-muted-foreground ${className}`} aria-label="No photo">
      <ImageOff className="size-6" strokeWidth={1.25} />
    </div>
  );
}

export function ItemCard({ item }: { item: Item }) {
  return (
    <Link href={`/items/${item.item_id}`} className="group flex flex-col overflow-hidden rounded-lg border bg-card transition-colors hover:border-foreground/25 focus-visible:ring-3 focus-visible:ring-ring/50 outline-none">
      <div className="relative aspect-[4/3] overflow-hidden bg-muted">
        <ItemThumb item={item} className="size-full transition duration-500 group-hover:scale-[1.02]" />
        <div className="absolute left-3 top-3 flex gap-1.5"><StatusBadge value={item.item_type} />{item.status !== "open" && <StatusBadge value={item.status} />}</div>
        {item.similarity != null && (
          <div className="absolute bottom-3 right-3 flex items-center gap-1 rounded-full bg-background/90 px-2.5 py-1 text-xs font-medium">
            <Sparkles className="size-3 text-primary" />{Math.round(item.similarity * 100)}% similar
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-5">
        <h3 className="line-clamp-1 text-[15px] font-medium tracking-tight">{item.title}</h3>
        <p className="line-clamp-2 min-h-10 text-sm leading-5 text-muted-foreground">{item.description}</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><MapPin className="size-3" />{item.location_name}</span>
          <span className="flex items-center gap-1"><CalendarDays className="size-3" />{fmtDate(item.date_lost_or_found)}</span>
        </div>
        <div className="mt-auto pt-2"><span className="eyebrow">{CATEGORY_LABEL[item.category] ?? item.category}</span></div>
      </div>
    </Link>
  );
}
