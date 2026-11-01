"use client";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "@/components/states";
import { SimpleSelect } from "@/components/simple-select";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";

interface Entry { audit_id: number; table_name: string; row_pk: number; action: string; actor_name: string | null; old_data: Record<string, unknown> | null; new_data: Record<string, unknown> | null; changed_at: string }

function diff(e: Entry): string {
  if (e.action === "INSERT") return "created";
  if (e.action === "DELETE") return "deleted";
  const keys = Object.keys(e.new_data ?? {}).filter((k) => !["updated_at"].includes(k) && JSON.stringify(e.new_data![k]) !== JSON.stringify(e.old_data?.[k]));
  return keys.map((k) => `${k}: ${JSON.stringify(e.old_data?.[k])} → ${JSON.stringify(e.new_data![k])}`).join(", ");
}

export default function Audit() {
  const [table, setTable] = useState("all");
  const [row, setRow] = useState("");
  const q = useQuery(() => api.get<{ entries: Entry[] }>(`/staff/audit?limit=200${table !== "all" ? `&table_name=${table}` : ""}${row ? `&row_pk=${Number(row)}` : ""}`), [table, row]);
  return (
    <div>
      <PageHeader title="Audit log" description="Every change to items, claims, matches and user accounts: who, what, when. Written by database triggers." />
      <div className="mb-4 flex flex-wrap gap-2">
        <SimpleSelect size="sm" className="w-40" value={table} onChange={setTable} options={[{ value: "all", label: "All tables" }, ...["item", "claim", "match", "users"].map((t) => ({ value: t, label: t }))]} />
        <Input aria-label="Row id" inputMode="numeric" placeholder="Row id" value={row} onChange={(e) => setRow(e.target.value.replace(/\D/g, ""))} className="h-7 w-28" />
      </div>
      {q.loading ? <ListSkeleton /> : q.error ? <ErrorState error={q.error} retry={q.reload} /> : !q.data?.entries.length ? <EmptyState title="No entries" /> : (
        <div className="overflow-x-auto rounded-xl border"><table className="w-full text-left text-sm">
          <thead className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground"><tr>{["When", "Who", "Table", "Row", "Action", "Change"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody>{q.data.entries.map((e) => (
            <tr key={e.audit_id} className="border-t align-top"><td className="whitespace-nowrap px-3 py-2 text-muted-foreground" title={e.changed_at}>{timeAgo(e.changed_at)}</td><td className="px-3 py-2">{e.actor_name ?? <span className="text-muted-foreground">system</span>}</td>
              <td className="px-3 py-2 font-mono text-xs">{e.table_name}</td><td className="tabular px-3 py-2">#{e.row_pk}</td><td className="px-3 py-2"><span className="rounded bg-secondary px-1.5 py-0.5 text-xs">{e.action}</span></td>
              <td className="max-w-md break-words px-3 py-2 font-mono text-xs text-muted-foreground">{diff(e)}</td></tr>))}</tbody></table></div>)}
    </div>
  );
}
