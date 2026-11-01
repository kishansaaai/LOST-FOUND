"use client";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { User } from "@/lib/types";

export default function ProfilePage() {
  const { allowed, user, reload } = useRequireAuth();
  if (!allowed || !user) return null;
  return <Profile user={user} reload={reload} />;      // mounted only once the user exists: state starts from props
}

function Profile({ user, reload }: { user: User; reload: () => Promise<void> }) {
  const [name, setName] = useState(user.name), [phone, setPhone] = useState(user.phone ?? "");
  const [cur, setCur] = useState(""), [next, setNext] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function save(key: string, body: object, ok: string) {
    setBusy(key);
    try { await api.patch("/auth/me", body); await reload(); toast.success(ok); if (key === "pw") { setCur(""); setNext(""); } }
    catch (e) { toast.error((e as Error).message); }
    setBusy(null);
  }
  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader title="Profile" />
      <Card><CardHeader><CardTitle>Your details</CardTitle><CardDescription className="flex items-center gap-2">{user.email}<StatusBadge value={user.role} /></CardDescription></CardHeader>
        <CardContent><form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save("profile", { name, phone }, "Profile updated"); }}>
          <div className="space-y-1.5"><Label htmlFor="n">Name</Label><Input id="n" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} /></div>
          <div className="space-y-1.5"><Label htmlFor="p">Phone</Label><Input id="p" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={40} /></div>
          <Button type="submit" disabled={busy === "profile"}>{busy === "profile" && <Loader2 className="size-4 animate-spin" />}Save changes</Button></form></CardContent></Card>
      <Card><CardHeader><CardTitle>Change password</CardTitle></CardHeader>
        <CardContent><form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save("pw", { current_password: cur, new_password: next }, "Password changed"); }}>
          <div className="space-y-1.5"><Label htmlFor="c">Current password</Label><Input id="c" type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" required /></div>
          <div className="space-y-1.5"><Label htmlFor="nw">New password</Label><Input id="nw" type="password" value={next} onChange={(e) => setNext(e.target.value)} minLength={8} autoComplete="new-password" required /></div>
          <Button type="submit" variant="outline" disabled={busy === "pw"}>{busy === "pw" && <Loader2 className="size-4 animate-spin" />}Update password</Button></form></CardContent></Card>
    </div>
  );
}
