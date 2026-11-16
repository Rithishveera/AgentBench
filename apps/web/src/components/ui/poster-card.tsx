import { cn } from "@/lib/utils";

interface PosterCardProps {
  shadow?: "teal" | "red";
  className?: string;
  children: React.ReactNode;
}

/**
 * PosterCard — vintage-poster double-frame card.
 * Outer: 2px tan border, radius 28px, hard-offset shadow.
 * Inner: 1px tan hairline 6px inset (via ::before in globals.css .poster-card).
 */
export function PosterCard({ shadow = "teal", className, children }: PosterCardProps) {
  return (
    <div
      className={cn(
        "poster-card relative overflow-hidden rounded-card border-2 border-tan bg-ink-raised",
        shadow === "teal" ? "shadow-teal" : "shadow-red",
        className,
      )}
    >
      {children}
    </div>
  );
}
