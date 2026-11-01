"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const TABS = [["/staff/claims", "Claim queue"], ["/staff/matches", "Matches"], ["/staff/analytics", "Analytics"], ["/staff/audit", "Audit log"]];

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  const { allowed } = useRequireAuth("staff");
  const path = usePathname();
  if (!allowed) return null;
  return (
    <div>
      <nav aria-label="Staff" className="mb-6 flex gap-1 overflow-x-auto border-b">
        {TABS.map(([href, label]) => (
          <Link key={href} href={href} aria-current={path.startsWith(href) ? "page" : undefined}
            className={cn("-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm transition", path.startsWith(href) ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>{label}</Link>))}
      </nav>
      {children}
    </div>
  );
}
