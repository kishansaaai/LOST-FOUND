"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";

function Form({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [f, setF] = useState({ name: "", email: "", password: "", phone: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const isLogin = mode === "login";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!isLogin && f.password.length < 8) return setError("Use at least 8 characters for your password.");
    setBusy(true);
    try {
      const u = isLogin ? await login(f.email, f.password) : await register(f.name, f.email, f.password, f.phone);
      toast.success(isLogin ? `Welcome back, ${u.name.split(" ")[0]}` : "Account created");
      router.push(next && next.startsWith("/") ? next : "/");
    } catch (err) {
      setError((err as Error).message);
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto mt-6 max-w-md">
      <Card>
        <CardHeader>
          <h1 className="text-xl font-medium leading-snug">{isLogin ? "Sign in" : "Create your account"}</h1>
          <CardDescription>{isLogin ? "Welcome back. Pick up where you left off." : "Report items and get automatic match suggestions."}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4" noValidate>
            {!isLogin && <div className="space-y-1.5"><Label htmlFor="name">Full name</Label><Input id="name" value={f.name} onChange={set("name")} required autoComplete="name" /></div>}
            <div className="space-y-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" value={f.email} onChange={set("email")} required autoComplete="email" /></div>
            <div className="space-y-1.5"><Label htmlFor="password">Password</Label><Input id="password" type="password" value={f.password} onChange={set("password")} required minLength={8} autoComplete={isLogin ? "current-password" : "new-password"} /></div>
            {!isLogin && <div className="space-y-1.5"><Label htmlFor="phone">Phone <span className="text-muted-foreground">(optional, shown to staff only)</span></Label><Input id="phone" type="tel" value={f.phone} onChange={set("phone")} autoComplete="tel" /></div>}
            {error && <p role="alert" className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" size="lg" disabled={busy}>{busy && <Loader2 className="size-4 animate-spin" />}{isLogin ? "Sign in" : "Create account"}</Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            {isLogin ? <>New here? <Link className="text-primary underline-offset-4 hover:underline" href="/register">Create an account</Link></>
              : <>Already registered? <Link className="text-primary underline-offset-4 hover:underline" href="/login">Sign in</Link></>}
          </p>
          {isLogin && <p className="mt-3 rounded-md bg-muted px-4 py-3 text-xs text-muted-foreground">Demo data loaded? Try <code>alice@lostfound.dev</code> or <code>staff@lostfound.dev</code> with password <code>Passw0rd!demo</code>.</p>}
        </CardContent>
      </Card>
    </div>
  );
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  return <Suspense><Form mode={mode} /></Suspense>;
}
