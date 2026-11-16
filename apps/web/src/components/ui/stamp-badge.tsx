import { cn } from "@/lib/utils";

interface StampBadgeProps {
  verdict: string;
  className?: string;
}

/**
 * StampBadge — rubber-stamp verdict badge.
 * Double tan border, -3deg rotation, stamp-in animation (160ms).
 * Animation disabled under prefers-reduced-motion (via globals.css).
 */
export function StampBadge({ verdict, className }: StampBadgeProps) {
  return (
    <span
      className={cn(
        "stamp-badge",
        "inline-flex items-center justify-center",
        "rounded-pill border-2 border-tan px-4 py-1.5",
        "outline outline-1 outline-tan outline-offset-[3px]",
        "text-sm font-black uppercase tracking-widest text-paper",
        "bg-ink-raised",
        className,
      )}
      aria-label={`Verdict: ${verdict}`}
    >
      {verdict}
    </span>
  );
}
