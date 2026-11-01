"use client";
import { toast } from "sonner";
import { ErrorState, ListSkeleton, PageHeader } from "@/components/states";
import { SimpleSelect } from "@/components/simple-select";
import { useQuery } from "@/hooks/use-query";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import type { Role } from "@/lib/types";

interface U { id: number; name: string; email: string; role: Role; created_at: string; items: number }

export default function Users() {
  const { allowed, user } = useRequireAuth("admin");
  const q = useQuery(() => api.get<{ users: U[] }>("/admin/users"), [], allowed);
  if (!allowed) return null;
  async function setRole(id: number, role: string) {
    try { await api.patch(`/admin/users/${id}/role`, { role }); toast.success("Role updated"); q.reload(); } catch (e) { toast.error((e as Error).message); q.reload(); }
  }
  return (
    <div>
      <PageHeader title="Users & roles" description="Roles are enforced in the API and in PostgreSQL (column grants + row-level security). The last admin cannot be demoted." />
      {q.loading ? <ListSkeleton /> : q.error ? <ErrorState error={q.error} retry={q.reload} /> : (
        <div className="overflow-x-auto rounded-lg border"><table className="w-full text-left text-sm">
          <thead className="bg-muted/60 text-[11px] uppercase tracking-[0.12em] text-muted-foreground"><tr>{["Name", "Email", "Reports", "Joined", "Role"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
          <tbody>{q.data!.users.map((u) => (
            <tr key={u.id} className="border-t"><td className="px-4 py-3 font-medium">{u.name}{u.id === user?.id && <span className="ml-2 text-xs text-muted-foreground">(you)</span>}</td><td className="px-4 py-3 text-muted-foreground">{u.email}</td><td className="tabular px-4 py-3">{u.items}</td><td className="px-4 py-3 text-muted-foreground">{fmtDate(u.created_at)}</td>
              <td className="px-4 py-3"><SimpleSelect size="sm" className="w-28" value={u.role} onChange={(v) => v !== u.role && setRole(u.id, v)} options={["user", "staff", "admin"].map((r) => ({ value: r, label: r }))} /></td></tr>))}</tbody></table></div>)}
    </div>
  );
}
