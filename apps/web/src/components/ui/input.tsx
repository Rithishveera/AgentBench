import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "control h-10 w-full rounded-md border border-tan bg-ink-raised px-3 text-sm text-paper",
        "outline-none placeholder:text-tan/60",
        className,
      )}
      {...props}
    />
  );
}
