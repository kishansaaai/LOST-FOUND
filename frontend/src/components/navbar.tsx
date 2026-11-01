"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bell, ClipboardCheck, LayoutDashboard, LogOut, Menu, Moon, PackageSearch, Plus, Shield, Sun, User as UserIcon, Users } from "lucide-react";
import { useTheme } from "next-themes";
import { Button, buttonVariants } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useNotificationCount } from "@/hooks/use-notifications";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/items", label: "Browse" },
  { href: "/report", label: "Report" },
];

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <Button variant="ghost" size="icon" aria-label="Toggle dark mode" onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
      <Sun className="size-4 dark:hidden" /><Moon className="hidden size-4 dark:block" />
    </Button>
  );
}

export function Navbar() {
  const { user, isStaff, logout, loading } = useAuth();
  const { count } = useNotificationCount();
  const path = usePathname();
  const router = useRouter();

  const links = [
    ...NAV,
    ...(user ? [{ href: "/my-items", label: "My reports" }, { href: "/claims", label: "My claims" }] : []),
    ...(isStaff ? [{ href: "/staff/claims", label: "Staff" }] : []),
  ];
  const active = (href: string) => path === href || (href !== "/" && path.startsWith(href.split("/").slice(0, 2).join("/")));

  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur supports-[backdrop-filter]:bg-background/75">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-5 sm:px-8">
        <Sheet>
          <SheetTrigger render={<Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu" />}><Menu className="size-5" /></SheetTrigger>
          <SheetContent side="left" className="w-64">
            <SheetHeader><SheetTitle>Lost &amp; Found</SheetTitle></SheetHeader>
            <nav className="flex flex-col gap-1 px-4 pb-6">
              {links.map((l) => <Link key={l.href} href={l.href} className={cn("rounded-md px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground", active(l.href) && "bg-muted font-medium text-foreground")}>{l.label}</Link>)}
            </nav>
          </SheetContent>
        </Sheet>

        <Link href="/" className="flex items-center gap-2.5 tracking-tight">
          <PackageSearch className="size-5 text-primary" strokeWidth={1.5} />
          <span className="hidden text-sm font-medium uppercase tracking-[0.14em] sm:inline">Lost &amp; Found</span>
        </Link>

        <nav className="ml-6 hidden items-center gap-1 md:flex" aria-label="Main">
          {links.map((l) => (
            <Link key={l.href} href={l.href} aria-current={active(l.href) ? "page" : undefined}
              className={cn("rounded-md px-4 py-3 text-sm text-muted-foreground transition-colors hover:text-foreground", active(l.href) && "text-foreground underline decoration-primary decoration-1 underline-offset-[10px]")}>{l.label}</Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1.5">
          <ThemeToggle />
          {user && (
            <Link href="/notifications" aria-label={`Notifications${count ? `, ${count} unread` : ""}`} className={cn(buttonVariants({ variant: "ghost", size: "icon" }), "relative")}>
              <Bell className="size-4" />
              {count > 0 && <span className="absolute -right-0.5 -top-0.5 grid min-w-4 place-items-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">{count > 99 ? "99+" : count}</span>}
            </Link>
          )}
          {loading ? null : user ? (
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="ghost" className="gap-2 px-2" />}>
                <span className="grid size-6 place-items-center rounded-full bg-accent text-xs font-medium text-accent-foreground">{user.name.slice(0, 1).toUpperCase()}</span>
                <span className="hidden max-w-28 truncate text-sm sm:inline">{user.name}</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuGroup><DropdownMenuLabel className="font-normal"><div className="font-medium">{user.name}</div><div className="truncate text-xs text-muted-foreground">{user.email}</div><div className="mt-1 text-xs capitalize text-primary">{user.role}</div></DropdownMenuLabel></DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => router.push("/profile")}><UserIcon className="size-4" />Profile</DropdownMenuItem>
                <DropdownMenuItem onClick={() => router.push("/my-items")}><ClipboardCheck className="size-4" />My reports</DropdownMenuItem>
                {isStaff && <DropdownMenuItem onClick={() => router.push("/staff/analytics")}><LayoutDashboard className="size-4" />Analytics</DropdownMenuItem>}
                {user.role === "admin" && <DropdownMenuItem onClick={() => router.push("/admin/users")}><Users className="size-4" />Users &amp; roles</DropdownMenuItem>}
                {isStaff && <DropdownMenuItem onClick={() => router.push("/staff/audit")}><Shield className="size-4" />Audit log</DropdownMenuItem>}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={async () => { await logout(); router.push("/"); }}><LogOut className="size-4" />Sign out</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <>
              <Link href="/login" className={buttonVariants({ variant: "ghost" })}>Sign in</Link>
              <Link href="/register" className={buttonVariants()}>Sign up</Link>
            </>
          )}
          {user && <Link href="/report" className={cn(buttonVariants(), "ml-1 hidden sm:inline-flex")}><Plus className="size-4" />Report</Link>}
        </div>
      </div>
    </header>
  );
}
