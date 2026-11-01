import { ImageIcon, Type } from "lucide-react";
import type { Explanation } from "@/lib/types";

/** Shows exactly how a match score was produced: the two rankings and their RRF terms. */
export function ScoreExplain({ e }: { e: Explanation }) {
  const strength = Math.round(e.confidence * 100);
  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="mb-1 flex items-baseline justify-between">
          <span className="font-medium">Match confidence</span><span className="tabular font-semibold">{strength}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={strength} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-primary" style={{ width: `${strength}%` }} />
        </div>
        <p className="mt-1 text-xs text-muted-foreground">How far the best similarity sits above the minimum needed to suggest a match. Candidates are ordered by the Reciprocal Rank Fusion score below.</p>
      </div>
      <ul className="space-y-2">
        {e.signals.map((s) => (
          <li key={s.signal} className="flex items-center gap-3 rounded-lg bg-muted/60 px-3 py-2">
            {s.signal === "text" ? <Type className="size-4 text-primary" /> : <ImageIcon className="size-4 text-primary" />}
            <div className="flex-1">
              <div className="font-medium capitalize">{s.signal} similarity</div>
              <div className="text-xs text-muted-foreground">cosine {s.similarity.toFixed(3)} · ranked #{s.rank} of the candidates</div>
            </div>
            <div className="tabular text-xs text-muted-foreground">+{s.contribution.toFixed(5)}</div>
          </li>
        ))}
      </ul>
      <p className="rounded-lg border bg-card px-3 py-2 font-mono text-xs">RRF = {e.formula}{e.boost > 0 && <span className="text-muted-foreground"> · tie-break boost +{e.boost.toFixed(4)}</span>}</p>
    </div>
  );
}
