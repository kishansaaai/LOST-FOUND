export const fmtDate = (d: string) =>
  new Date(d.length === 10 ? `${d}T00:00:00` : d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

export function timeAgo(iso: string): string {
  const s = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  const units: [number, string][] = [[31536000, "y"], [2592000, "mo"], [86400, "d"], [3600, "h"], [60, "m"]];
  for (const [n, u] of units) if (s >= n) return `${Math.floor(s / n)}${u} ago`;
  return "just now";
}

export const pct = (v: number | null | undefined, digits = 0) => (v == null ? "–" : `${(v * 100).toFixed(digits)}%`);
export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
