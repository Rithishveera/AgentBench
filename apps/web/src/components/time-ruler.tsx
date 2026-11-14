"use client";

import { useState, type KeyboardEvent, type MouseEvent } from "react";
import type { FaultRecord, RunRecord, StepSummary } from "@/lib/api-server";

type Slice = { start: number; end: number; kind: "llm" | "tool" | "wait"; seq: number };

const colors = { llm: "#17664f", tool: "#e45c3a", wait: "#9aa8b2" };

function timelineSlices(steps: StepSummary[], run: RunRecord, complete: boolean) {
  const runStart = run.started_at ? Date.parse(run.started_at) : NaN;
  const knownDuration = Math.max(Number(run.duration_ms || 0), 1);
  const slices: Slice[] = [];
  let cursor = 0;
  const ordered = [...steps].sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts));

  for (const step of ordered) {
    const timestamp = Date.parse(step.ts);
    const offset = Number.isFinite(runStart) && Number.isFinite(timestamp)
      ? Math.min(knownDuration, Math.max(cursor, timestamp - runStart))
      : cursor;
    if (offset > cursor) slices.push({ start: cursor, end: offset, kind: "wait", seq: step.seq });
    const end = Math.min(knownDuration, offset + step.duration_ms);
    if (end > offset) {
      const kind = step.type === "llm" ? "llm" : step.type === "tool" ? "tool" : "wait";
      const previous = slices[slices.length - 1];
      if (previous?.kind === kind && previous.end === offset) previous.end = end;
      else slices.push({ start: offset, end, kind, seq: step.seq });
      cursor = Math.max(cursor, end);
    }
  }
  if (complete && cursor < knownDuration) {
    slices.push({ start: cursor, end: knownDuration, kind: "wait", seq: ordered.at(-1)?.seq ?? 0 });
  }
  return { slices, total: knownDuration, runStart };
}

export function TimeRuler({
  steps,
  faults,
  run,
  complete,
  onJump,
}: Readonly<{
  steps: StepSummary[];
  faults: FaultRecord[];
  run: RunRecord;
  complete: boolean;
  onJump: (seq: number) => void;
}>) {
  const { slices, total, runStart } = timelineSlices(steps, run, complete);
  const orderedSteps = [...steps].sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts));
  const [selectedIndex, setSelectedIndex] = useState(0);

  function jumpToTime(ratio: number) {
    if (!orderedSteps.length) return;
    const time = ratio * total;
    const start = Number.isFinite(runStart) ? runStart : 0;
    let elapsed = 0;
    let closest = 0;
    let distance = Number.POSITIVE_INFINITY;
    orderedSteps.forEach((step, index) => {
      const timestamp = Date.parse(step.ts);
      const position = Number.isFinite(runStart) && Number.isFinite(timestamp)
        ? timestamp - start
        : elapsed;
      const delta = Math.abs(position - time);
      if (delta < distance) {
        closest = index;
        distance = delta;
      }
      elapsed += step.duration_ms;
    });
    setSelectedIndex(closest);
    onJump(orderedSteps[closest].seq);
  }

  function handleClick(event: MouseEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    if (bounds.width > 0) jumpToTime(Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)));
  }

  function handleKeyDown(event: KeyboardEvent<SVGSVGElement>) {
    if (!orderedSteps.length) return;
    let next = selectedIndex;
    if (event.key === "ArrowRight" || event.key === "ArrowUp") next = Math.min(orderedSteps.length - 1, selectedIndex + 1);
    else if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = Math.max(0, selectedIndex - 1);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = orderedSteps.length - 1;
    else return;
    event.preventDefault();
    setSelectedIndex(next);
    onJump(orderedSteps[next].seq);
  }

  return (
    <div className="time-ruler" aria-label="Run time ruler">
      <svg
        className="ruler-svg"
        viewBox="0 0 1000 18"
        role="slider"
        tabIndex={0}
        aria-label="Run timeline ruler"
        aria-valuemin={0}
        aria-valuemax={Math.max(orderedSteps.length - 1, 0)}
        aria-valuenow={Math.min(selectedIndex, Math.max(orderedSteps.length - 1, 0))}
        aria-valuetext={orderedSteps.length ? `Step ${orderedSteps[selectedIndex]?.seq + 1} of ${run.steps_count}` : "No steps"}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
      >
        {slices.map((slice, index) => {
          const x = (slice.start / total) * 1000;
          const width = Math.max((slice.end - slice.start) / total * 1000, 1);
          return (
            <rect
              key={`${slice.seq}-${index}`}
              x={x}
              y={1}
              width={width}
              height={16}
              rx={2}
              fill={colors[slice.kind]}
            />
          );
        })}
        {faults.map((fault) => {
          const timestamp = Date.parse(fault.ts);
          const position = Number.isFinite(runStart)
            ? Math.min(1000, Math.max(0, ((timestamp - runStart) / total) * 1000))
            : 0;
          return (
            <g key={`fault-${fault.seq}`} aria-label={`${fault.fault_type}, ${fault.agent_reaction ?? "unclassified"}`}>
              <line x1={position} x2={position} y1={0} y2={18} stroke="#9b3d2c" strokeWidth={2} />
              <title>{fault.fault_type}: {fault.agent_reaction ?? "unclassified"}</title>
            </g>
          );
        })}
      </svg>
      <div className="ruler-legend" aria-hidden="true">
        <span><i className="legend-llm" />LLM</span>
        <span><i className="legend-tool" />Tool</span>
        <span><i className="legend-wait" />Waiting</span>
        {faults.length > 0 && <span><i className="legend-fault" />Injected fault</span>}
        <span className="ml-auto">{(total / 1000).toFixed(1)}s</span>
      </div>
    </div>
  );
}