"use client";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface Option { value: string; label: string }

/** Thin wrapper over the Base UI select that shows the option LABEL in the trigger. */
export function SimpleSelect({ value, onChange, options, placeholder, className, id, size }: {
  value: string; onChange: (v: string) => void; options: Option[]; placeholder?: string; className?: string; id?: string;
  size?: "sm" | "default";
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange((v as string) ?? "")} items={options}>
      <SelectTrigger id={id} className={className ?? "w-full"} size={size}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}
