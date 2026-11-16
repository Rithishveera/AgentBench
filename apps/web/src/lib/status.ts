import {
  Check,
  X,
  Clock,
  Zap,
  Wrench,
  Ellipsis,
  HelpCircle,
  type LucideIcon,
} from "lucide-react";
import { VinylSpinner } from "@/components/ui/vinyl-spinner";

/**
 * Status_Module — single source of truth for run status presentation.
 * Maps every RunStatus to: colorToken, tailwindBg, icon, label, and optional hatch.
 *
 * Color is NEVER the sole signal: every entry includes an icon and a label.
 */

export type RunStatus =
  | "passed"
  | "failed"
  | "timeout"
  | "agent_error"
  | "infra_error"
  | "running"
  | "queued";

export type HatchPattern = "red-45deg-4px" | "tan-45deg-4px";

export interface StatusEntry {
  status: RunStatus | "unknown";
  /** CSS custom-property reference, e.g. "var(--color-teal)" */
  colorToken: string;
  /** Tailwind utility class for background */
  tailwindBg: string;
  /** Lucide icon component */
  icon: LucideIcon | typeof VinylSpinner;
  /** Human-readable label */
  label: string;
  /** Optional 45-degree hatch overlay */
  hatch?: HatchPattern;
  /** True when the entry uses an outline style rather than a fill */
  outline?: boolean;
}

export const STATUS_MAP: Record<RunStatus, StatusEntry> = {
  passed: {
    status: "passed",
    colorToken: "var(--color-teal)",
    tailwindBg: "bg-teal",
    icon: Check,
    label: "Passed",
  },
  failed: {
    status: "failed",
    colorToken: "var(--color-red)",
    tailwindBg: "bg-red",
    icon: X,
    label: "Failed",
  },
  timeout: {
    status: "timeout",
    colorToken: "var(--color-tan)",
    tailwindBg: "bg-tan",
    icon: Clock,
    label: "Timeout",
    outline: true,
  },
  agent_error: {
    status: "agent_error",
    colorToken: "var(--color-red)",
    tailwindBg: "bg-red",
    icon: Zap,
    label: "Agent error",
    hatch: "red-45deg-4px",
  },
  infra_error: {
    status: "infra_error",
    colorToken: "var(--color-ink-raised)",
    tailwindBg: "bg-ink-raised",
    icon: Wrench,
    label: "Infra error",
    hatch: "tan-45deg-4px",
  },
  running: {
    status: "running",
    colorToken: "var(--color-tan)",
    tailwindBg: "bg-transparent",
    icon: VinylSpinner as unknown as LucideIcon,
    label: "Running",
    outline: true,
  },
  queued: {
    status: "queued",
    colorToken: "var(--color-tan)",
    tailwindBg: "bg-transparent",
    icon: Ellipsis,
    label: "Queued",
    outline: true,
  },
};

const FALLBACK_ENTRY: StatusEntry = {
  status: "unknown",
  colorToken: "var(--color-paper)",
  tailwindBg: "bg-paper",
  icon: HelpCircle,
  label: "Unknown",
};

/**
 * Returns the StatusEntry for a given status string.
 * Returns FALLBACK_ENTRY for any value not in STATUS_MAP.
 */
export function getStatusEntry(status: string): StatusEntry {
  return (STATUS_MAP as Record<string, StatusEntry>)[status] ?? FALLBACK_ENTRY;
}

/**
 * Returns the hatch background-image CSS value for the given pattern.
 */
export function hatchStyle(pattern: HatchPattern): React.CSSProperties {
  const color =
    pattern === "red-45deg-4px"
      ? "color-mix(in srgb, var(--color-red) 30%, transparent)"
      : "color-mix(in srgb, var(--color-tan) 30%, transparent)";
  return {
    backgroundImage: `repeating-linear-gradient(45deg, transparent, transparent 3px, ${color} 3px, ${color} 4px)`,
  };
}
