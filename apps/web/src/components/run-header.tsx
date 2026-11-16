import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { StampBadge } from "@/components/ui/stamp-badge";
import { VinylSpinner } from "@/components/ui/vinyl-spinner";
import type { CursorPage, FaultRecord, RunRecord } from "@/lib/api-server";
import { getStatusEntry } from "@/lib/status";

export function RunHeader({
  run,
  agentName,
  initialFaults,
}: Readonly<{
  run: RunRecord;
  agentName: string;
  initialFaults: CursorPage<FaultRecord> | null;
}>) {
  const counts = (initialFaults?.items ?? []).reduce<Record<string, number>>((summary, fault) => {
    summary[fault.fault_type] = (summary[fault.fault_type] ?? 0) + 1;
    return summary;
  }, {});
  const faultTotal = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const faultCount = `${faultTotal.toLocaleString()}${initialFaults?.next_cursor !== null && initialFaults?.next_cursor !== undefined ? "+" : ""}`;

  const statusEntry = getStatusEntry(run.verdict ? (run.verdict.passed ? "passed" : "failed") : run.status);
  const isRunning = run.status === "running";

  return (
    <>
      <div className="page-heading run-heading">
        <div>
          <Link className="mb-3 inline-flex text-xs font-semibold text-tan hover:text-paper" href={`/benchmarks/${run.benchmark_id}`}>Back to benchmark</Link>
          <p className="eyebrow">Run inspector</p>
          <h1>{agentName}</h1>
          <p className="page-subtitle"><span className="mono">{run.task_id}</span> · Attempt {run.attempt_no} · <span className="mono">{run.id}</span></p>
        </div>
        <div className="flex items-center gap-3">
          {isRunning ? (
            <VinylSpinner size={28} />
          ) : run.verdict ? (
            <StampBadge verdict={run.verdict.passed ? "Passed" : "Failed"} />
          ) : (
            <Badge status={run.status}>
              <statusEntry.icon size={13} aria-hidden="true" />
              {statusEntry.label}
            </Badge>
          )}
        </div>
      </div>
      <div className="run-metrics" aria-label="Run summary">
        <Metric label="Cost" value={`$${Number(run.cost_usd || 0).toFixed(3)}`} />
        <Metric label="Duration" value={run.duration_ms == null ? "—" : `${(run.duration_ms / 1000).toFixed(1)}s`} />
        <Metric label="Steps" value={run.steps_count.toLocaleString()} />
        <Metric label="Tokens in / out" value={`${run.tokens_in.toLocaleString()} / ${run.tokens_out.toLocaleString()}`} />
        <Metric label="Faults" value={faultCount} detail={Object.entries(counts).map(([type, count]) => `${type} ${count}`).join(" · ") || "None"} />
      </div>
    </>
  );
}

function Metric({ label, value, detail }: Readonly<{ label: string; value: string; detail?: string }>) {
  return <div className="summary-tile"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}
