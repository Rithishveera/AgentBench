import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const styles = cva(
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-pill px-4 text-sm font-semibold transition-colors disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        solid:   "bg-red text-paper hover:bg-red/80",
        outline: "border border-tan bg-transparent text-paper hover:bg-tan/10",
        quiet:   "bg-transparent text-teal-glow hover:bg-teal/10",
        danger:  "bg-red text-paper hover:bg-red/80",
        ghost:   "bg-transparent text-ink-raised hover:bg-ink-raised/50",
      },
      size: {
        default: "",
        small:   "min-h-8 px-3 text-xs",
        icon:    "size-10 p-0",
      },
    },
    defaultVariants: { variant: "solid", size: "default" },
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof styles>;

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(styles({ variant, size }), className)} {...props} />;
}
