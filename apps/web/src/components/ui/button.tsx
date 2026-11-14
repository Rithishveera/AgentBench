import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const styles = cva(
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition-colors disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        solid: "bg-forest text-white hover:bg-[#10513e]",
        outline: "border border-line bg-white text-ink hover:bg-paper",
        quiet: "text-muted hover:bg-paper hover:text-ink",
        danger: "bg-signal text-white hover:bg-[#c84b2e]",
      },
      size: { default: "", small: "min-h-8 px-3 text-xs", icon: "size-10 p-0" },
    },
    defaultVariants: { variant: "solid", size: "default" },
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof styles>;

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(styles({ variant, size }), className)} {...props} />;
}