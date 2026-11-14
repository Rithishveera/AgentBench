"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, RotateCw } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Agent, Benchmark, BenchmarkRun } from "@/lib/api-server";

type Detail = {
  benchmark: Benchmark;
  runs: { items: BenchmarkRun[]; next_cursor: string | null };
};
type Summary = {
  overall?: {
    success_rate?: number;
    n?: number;
    duration_ms?: { p95?: number };
    cost_per_success_usd?: number;
  };
  status_breakdown?: Record<string, number>;
};

function statusTone(status: string) {
  if (status === "completed") return "success" as const;
  if (["agent_error", "timeout", "failed"].includes(status)) return "danger" as const;
  if (status === "running") return "info" as const;
  return "neutral" as const;
}

export function BenchmarkMonitor({
  benchmarkId,
  initialBenchmark,
  initialRuns,
  agents,
  loadError,
}: Readonly<{
  benchmarkId: string;
  initialBenchmark: Benchmark | null;
  initialRuns: Detail["runs"];
  agents: Agent[];
  loadError: boolean;
}>) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const cursor = cursors[cursors.length - 1];
  const query = useQuery({
    queryKey: ["benchmark", benchmarkId, cursor],
    queryFn: async () => {
      const suffix = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
      const response = await fetch(`/api/benchmarks/${encodeURIComponent(benchmarkId)}${suffix}`);
      if (!response.ok) throw new Error("Benchmark status could not be refreshed");
      return (await response.json()) as Detail;
    },
    initialData: cursor === null && initialBenchmark ? { benchmark: initialBenchmark, runs: initialRuns } : undefined,
    refetchInterval: (current) => {
      const status = current.state.data?.benchmark.status;
      return status === "completed" || status === "failed" ? false : 3000;
    },
  });
  const data = query.data;
  const summary = (data?.benchmark.summary ?? {}) as Summary;
  const overview = summary.overall;
  const counts = summary.status_breakdown ?? {};
  const agentNames = useMemo(() => new Map(agents.map((agent) => [agent.id, agent.name])), [agents]);
  const terminal = ["completed", "failed"].includes(data?.benchmark.status ?? "");
  const percent = useMemo(() => {
    const total = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
    const done = Number(counts.completed || 0) + Number(counts.agent_error || 0) + Number(counts.timeout || 0) + Number(counts.infra_error || 0);
    return total ? Math.round((done / total) * 100) : 0;
  }, [counts]);

  if (!data && (loadError || query.isError)) {
    return <div className="surface empty-state" role="alert">Benchmark data is unavailable. Check the ID or API connection.</div>;
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <Link className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-forest" href="/"><ArrowLeft size={14} />Leaderboard</Link>
          <p className="eyebrow">Benchmark run</p>
          <h1>Execution status</h1>
          <p className="page-subtitle mono">{benchmarkId}</p>
        </div>
        <div className="toolbar-group">
          {data && <Badge tone={statusTone(data.benchmark.status)}>{data.benchmark.status}</Badge>}
          <Button variant="outline" size="small" onClick={() => void query.refetch()} aria-label="Refresh benchmark status"><RotateCw size={14} /></Button>
        </div>
      </div>

      <div className="summary-grid" aria-label="Benchmark summary">
        <div className="summary-tile"><span>Success rate</span><strong>{overview?.success_rate === undefined ? "—" : `${(overview.success_rate * 100).toFixed(1)}%`}</strong></div>
        <div className="summary-tile"><span>Scored runs</span><strong>{overview?.n ?? "—"}</strong></div>
        <div className="summary-tile"><span>P95 latency</span><strong>{overview?.duration_ms?.p95 === undefined ? "—" : `${(overview.duration_ms.p95 / 1000).toFixed(1)}s`}</strong></div>
        <div className="summary-tile"><span>Cost / success</span><strong>{overview?.cost_per_success_usd === undefined ? "—" : `$${overview.cost_per_success_usd.toFixed(3)}`}</strong></div>
      </div>

      <section className="surface" aria-labelledby="runs-title">
        <div className="surface-header">
          <div><h2 className="section-title" id="runs-title">Run status</h2><p className="section-note">{terminal ? "All runs are terminal." : `Refreshing every 3 seconds · ${percent}% terminal`}</p></div>
          <Badge tone={terminal ? "success" : "info"}>{terminal ? "Complete" : "Live"}</Badge>
        </div>
        {data?.runs.items.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th scope="col">Agent</th><th scope="col">Task</th><th scope="col">Attempt</th><th scope="col">Mode</th><th scope="col">Status</th><th scope="col">Duration</th><th scope="col">Cost</th></tr></thead>
              <tbody>
                {data.runs.items.map((run) => (
                  <tr key={run.id}>
                    <td>{agentNames.get(run.agent_id) ?? run.agent_id.slice(0, 8)}</td>
                    <td className="mono"><Link className="text-forest underline-offset-2 hover:underline" href={`/runs/${run.id}`}>{run.task_id}</Link></td>
                    <td>{run.attempt_no}</td>
                    <td><Badge tone={run.fault_mode === "faulted" ? "warning" : "neutral"}>{run.fault_mode}</Badge></td>
                    <td><Badge tone={statusTone(run.status)}>{run.status}</Badge></td>
                    <td>{run.duration_ms == null ? "—" : `${(run.duration_ms / 1000).toFixed(1)}s`}</td>
                    <td>${Number(run.cost_usd || 0).toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="empty-state">Runs will appear as soon as the benchmark is queued.</div>}
        <div className="surface-header border-t-0 border-b-0">
          <Button variant="outline" size="small" disabled={cursors.length < 2} onClick={() => setCursors((value) => value.slice(0, -1))}>Previous</Button>
          <span className="stepper">Page {cursors.length}</span>
          <Button variant="outline" size="small" disabled={!data?.runs.next_cursor} onClick={() => data?.runs.next_cursor && setCursors((value) => [...value, data.runs.next_cursor!])}>Next</Button>
        </div>
      </section>
    </>
  );
}