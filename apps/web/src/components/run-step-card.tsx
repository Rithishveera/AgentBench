"use client";

import { ChevronDown, ChevronRight, CircleAlert } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { StepPayloadDetail } from "@/components/step-payload-detail";
import type { StepSummary } from "@/lib/api-server";
import { formatUtcTime } from "@/lib/utils";

const stepTypeTone = {
  llm:   "info",
  tool:  "neutral",
  retry: "warning",
} as const;

export function RunStepCard({
  runId,
  step,
  registerButton,
  onArrow,
}: Readonly<{
  runId: string;
  step: StepSummary;
  registerButton: (seq: number, element: HTMLButtonElement | null) => void;
  onArrow: (seq: number, direction: -1 | 1) => void;
}>) {
  const [expanded, setExpanded] = useState(false);
  const tone = stepTypeTone[step.type as keyof typeof stepTypeTone] ?? "neutral";
  return (
    <article className={`timeline-card ${step.ok ? "" : "timeline-card-failed"}`}>
      <div className="timeline-pin" aria-hidden="true"><span /></div>
      <button
        className="timeline-step-toggle"
        ref={(element) => registerButton(step.seq, element)}
        aria-expanded={expanded}
        aria-controls={`step-payload-${step.seq}`}
        onClick={() => setExpanded((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            onArrow(step.seq, event.key === "ArrowDown" ? 1 : -1);
          }
        }}
      >
        <span className="timeline-toggle-icon" aria-hidden="true">{expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</span>
        <span className="timeline-step-main">
          <span className="timeline-step-title">
            <span className="metric-main">{step.short_label}</span>
            <Badge tone={tone}>{step.type}</Badge>
            {!step.ok && <Badge tone="danger"><CircleAlert size={12} />Failed</Badge>}
            {step.truncated && <Badge tone="warning">Truncated</Badge>}
          </span>
          <span className="timeline-step-meta">
            <time dateTime={step.ts}>{formatUtcTime(step.ts)}</time>
            <span>{step.duration_ms.toLocaleString()} ms</span>
            <span>Step {step.seq + 1}</span>
          </span>
        </span>
      </button>
      {expanded && <div id={`step-payload-${step.seq}`} className="timeline-payload"><StepPayloadDetail runId={runId} step={step} /></div>}
    </article>
  );
}
