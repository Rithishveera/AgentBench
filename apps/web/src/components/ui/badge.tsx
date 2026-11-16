import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { getStatusEntry, hatchStyle, type RunStatus } from "@/lib/status";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  /** Use status= for run status badges; tone= for legacy/generic use */
  status?: RunStatus | string;
  /** Legacy tone prop — mapped to status palette */
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}

const toneToStatus: Record<string, RunStatus> = {
  success: "passed",
  danger:  "failed",
  warning: "timeout",
  info:    "running",
  neutral: "queued",
};

export function Badge({ status, tone, className, ...props }: BadgeProps) {
  const resolvedStatus = status ?? (tone ? toneToStatus[tone] : undefined) ?? "queued";
  const entry = getStatusEntry(resolvedStatus);
  const isHatched = Boolean(entry.hatch);
  const isOutline = Boolean(entry.outline);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill px-2.5 py-1 text-xs font-semibold",
        isOutline
          ? "border border-tan bg-transparent text-paper"
          : `${entry.tailwindBg} text-paper`,
        className,
      )}
      style={isHatched && entry.hatch ? hatchStyle(entry.hatch) : undefined}
      {...props}
    />
  );
}
