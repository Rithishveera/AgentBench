import { cn } from "@/lib/utils";

interface HalftoneDividerProps {
  /** A palette color token reference, e.g. "var(--color-tan)" or "var(--color-red)" */
  color: string;
  className?: string;
}

/**
 * HalftoneDivider — CSS radial-gradient halftone dot pattern.
 * Used for fault/error regions and section dividers.
 * Accepts a palette color token as required prop.
 */
export function HalftoneDivider({ color, className }: HalftoneDividerProps) {
  return (
    <div
      aria-hidden="true"
      className={cn("h-6 w-full", className)}
      style={{
        "--dot-color": color,
        background: "radial-gradient(circle, var(--dot-color) 1.5px, transparent 1.5px)",
        backgroundSize: "8px 8px",
        opacity: 0.4,
      } as React.CSSProperties}
    />
  );
}
