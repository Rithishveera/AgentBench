import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "control h-10 w-full rounded-md border border-tan bg-ink-raised px-3 text-sm text-paper",
        "outline-none appearance-none",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
