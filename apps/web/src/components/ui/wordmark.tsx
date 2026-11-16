import Link from "next/link";
import { cn } from "@/lib/utils";

interface WordmarkProps {
  size?: "sm" | "md" | "lg";
  className?: string;
  href?: string;
}

const sizes = {
  sm: { text: "text-sm",     svg: 20 },
  md: { text: "text-lg",     svg: 28 },
  lg: { text: "text-display", svg: 40 },
};

/**
 * Wordmark — "AGENTBENCH" in display style alongside vinyl-record mark.
 */
export function Wordmark({ size = "md", className, href = "/" }: WordmarkProps) {
  const { text, svg } = sizes[size];
  const cx = svg / 2;
  const r = svg / 2 - 1;

  const inner = (
    <span className={cn("flex items-center gap-2", className)}>
      {/* Vinyl mark */}
      <svg
        width={svg}
        height={svg}
        viewBox={`0 0 ${svg} ${svg}`}
        aria-hidden="true"
        className="shrink-0"
      >
        <circle cx={cx} cy={cx} r={r} fill="var(--color-ink)" stroke="var(--color-tan)" strokeWidth={1.5} />
        <circle cx={cx} cy={cx} r={r * 0.65} fill="none" stroke="var(--color-ink-raised)" strokeWidth={1.2} />
        <circle cx={cx} cy={cx} r={r * 0.42} fill="none" stroke="var(--color-ink-raised)" strokeWidth={1.2} />
        <circle cx={cx} cy={cx} r={r * 0.22} fill="var(--color-red)" />
        <circle cx={cx} cy={cx} r={r * 0.07} fill="var(--color-ink)" />
      </svg>
      {/* Wordmark text */}
      <span
        className={cn(text, "font-black uppercase tracking-tight text-paper")}
        style={{ fontStretch: "75%" }}
      >
        AGENTBENCH
      </span>
    </span>
  );

  return href ? <Link href={href}>{inner}</Link> : inner;
}
