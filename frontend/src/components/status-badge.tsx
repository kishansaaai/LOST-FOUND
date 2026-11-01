import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { titleCase } from "@/lib/format";

const POS = "bg-accent text-accent-foreground";
const NEU = "bg-muted text-muted-foreground";
const ATT = "bg-transparent text-foreground ring-1 ring-inset ring-foreground/20";
const NEG = "bg-destructive/10 text-destructive";

const TONE: Record<string, string> = {
  lost: ATT, found: POS, open: ATT, matched: POS, claimed: POS, returned: POS, closed: NEU,
  pending: ATT, under_review: ATT, verified: POS, approved: POS, rejected: NEG, denied: NEG,
  suggested: ATT, confirmed: POS,
};

export function StatusBadge({ value, className }: { value: string; className?: string }) {
  return <Badge variant="secondary" className={cn("h-5 rounded-full border-0 px-2 text-[11px] font-medium tracking-wide", TONE[value] ?? NEU, className)}>{titleCase(value)}</Badge>;
}
