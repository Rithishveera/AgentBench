"use client";

import dynamic from "next/dynamic";
import type { CursorPage, FaultRecord, RunRecord, StepSummary } from "@/lib/api-server";

const RunInspector = dynamic(
  () => import("@/components/run-inspector").then((module) => module.RunInspector),
  { ssr: false, loading: () => <div className="surface empty-state">Preparing the interactive timeline…</div> },
);

export function RunTimelineIsland({
  run,
  initialSteps,
  initialFaults,
}: Readonly<{
  run: RunRecord;
  initialSteps: CursorPage<StepSummary> | null;
  initialFaults: CursorPage<FaultRecord> | null;
}>) {
  return <RunInspector run={run} initialSteps={initialSteps} initialFaults={initialFaults} />;
}