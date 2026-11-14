import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn("control h-10 w-full rounded-md border border-line bg-white px-3 text-sm text-ink outline-none focus:border-forest focus:ring-2 focus:ring-forest/15", className)}
      {...props}
    />
  );
}