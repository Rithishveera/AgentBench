import { cn } from "@/lib/utils";

interface VinylSpinnerProps {
  size?: number;
  className?: string;
}

/**
 * VinylSpinner — spinning vinyl-record loading indicator.
 * Black disc, 3 concentric groove rings, red center label.
 * Rotates at 33 rpm (1818ms per revolution) via globals.css .vinyl-spinner.
 * Static under prefers-reduced-motion.
 */
export function VinylSpinner({ size = 32, className }: VinylSpinnerProps) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 1;
  const grooveGap = r / 4;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      aria-label="Loading"
      role="img"
      className={cn("vinyl-spinner", className)}
      style={{ display: "inline-block" }}
    >
      {/* Disc */}
      <circle cx={cx} cy={cy} r={r} fill="var(--color-ink)" />
      {/* Groove rings */}
      <circle cx={cx} cy={cy} r={r * 0.75} fill="none" stroke="var(--color-ink-raised)" strokeWidth={1.5} />
      <circle cx={cx} cy={cy} r={r * 0.55} fill="none" stroke="var(--color-ink-raised)" strokeWidth={1.5} />
      <circle cx={cx} cy={cy} r={r * 0.35} fill="none" stroke="var(--color-ink-raised)" strokeWidth={1.5} />
      {/* Red center label */}
      <circle cx={cx} cy={cy} r={r * 0.18} fill="var(--color-red)" />
      {/* Center hole */}
      <circle cx={cx} cy={cy} r={r * 0.05} fill="var(--color-ink)" />
    </svg>
  );
}
