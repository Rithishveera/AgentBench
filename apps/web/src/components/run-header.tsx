import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import type { CursorPage, FaultRecord, RunRecord } from "@/lib/api-server";

function statusTone(run: RunRecord) {
  if (run.verdict?.passed) return "success" as const;
  if (["agent_error", "timeout", "infra_error"].includes(run.status)) return "danger" as const;
  if (run.status === "running") return "info" as const;
  return "neutral" as const;
}

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
  return (
    <>
      <div className="page-heading run-heading">
        <div>
          <Link className="mb-3 inline-flex text-xs font-semibold text-slate-500 hover:text-forest" href={`/benchmarks/${run.benchmark_id}`}>Back to benchmark</Link>
          <p className="eyebrow">Run inspector</p>
          <h1>{agentName}</h1>
          <p className="page-subtitle"><span className="mono">{run.task_id}</span> · Attempt {run.attempt_no} · <span className="mono">{run.id}</span></p>
        </div>
        <Badge tone={statusTone(run)}>{run.verdict ? run.verdict.passed ? "Passed" : "Failed" : run.status}</Badge>
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