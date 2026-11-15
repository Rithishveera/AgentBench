"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, RotateCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Agent, Benchmark, BenchmarkRun } from "@/lib/api-server";
import { getStatusEntry } from "@/lib/status";
import { useRunStream, type StreamMessage, type StreamSnapshot } from "@/hooks/use-run-stream";

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

function isTerminal(status: string) {
  return status === "completed" || status === "failed";
}

// --- Progress matrix -------------------------------------------------------

type RunMap = Map<string, BenchmarkRun>;

function mergeRunUpdate(
  runs: RunMap,
  update: { run_id: string; agent_id: string; task_id: string; status: string; passed?: boolean; cost_usd?: number },
): RunMap {
  const next = new Map(runs);
  const existing = next.get(update.run_id);
  if (existing) {
    next.set(update.run_id, {
      ...existing,
      status: update.status,
      verdict: update.passed !== undefined ? { passed: update.passed } : existing.verdict,
      cost_usd: update.cost_usd ?? existing.cost_usd,
    });
  }
  return next;
}

function runMapFromList(items: BenchmarkRun[]): RunMap {
  return new Map(items.map((r) => [r.id, r]));
}

function ProgressMatrix({
  runs,
  agents,
  tasks,
}: {
  runs: RunMap;
  agents: Map<string, string>; // id -> name
  tasks: string[];
}) {
  if (tasks.length === 0) return null;
  const agentIds = Array.from(
    new Set(Array.from(runs.values()).map((r) => r.agent_id)),
  );
  if (agentIds.length === 0) return null;

  return (
    <div className="table-wrap">
      <table className="data-table" aria-label="Run progress matrix">
        <thead>
          <tr>
            <th scope="col">Agent</th>
            {tasks.map((t) => (
              <th key={t} scope="col" className="text-xs">
                {t.length > 18 ? `…${t.slice(-15)}` : t}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {agentIds.map((agentId) => (
            <tr key={agentId}>
              <td className="metric-main">{agents.get(agentId) ?? agentId.slice(0, 8)}</td>
              {tasks.map((taskId) => {
                // Find the first matching run for this agent+task (attempt 1, non-paired baseline)
                const run = Array.from(runs.values()).find(
                  (r) => r.agent_id === agentId && r.task_id === taskId && r.fault_mode === "none",
                ) ?? Array.from(runs.values()).find(
                  (r) => r.agent_id === agentId && r.task_id === taskId,
                );
                if (!run) return <td key={taskId} className="text-tan">—</td>;
                const entry = getStatusEntry(run.status);
                return (
                  <td key={taskId}>
                    <span className="inline-flex items-center gap-1 text-xs" title={entry.label}>
                      <entry.icon size={12} aria-hidden="true" />
                      <span className="sr-only">{entry.label}</span>
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- ETA estimate ----------------------------------------------------------

function computeEta(runs: RunMap, createdAt: string | null): string | null {
  const values = Array.from(runs.values());
  const finished = values.filter((r) => r.duration_ms != null && r.duration_ms > 0);
  if (finished.length === 0 || !createdAt) return null;
  const durations = finished.map((r) => Number(r.duration_ms)).sort((a, b) => a - b);
  const median = durations[Math.floor(durations.length / 2)] ?? 0;
  const remaining = values.filter((r) => r.status === "queued" || r.status === "running").length;
  if (remaining === 0) return null;
  const etaMs = remaining * median;
  const etaSec = Math.round(etaMs / 1000);
  if (etaSec < 60) return `~${etaSec}s`;
  return `~${Math.round(etaSec / 60)}m`;
}

// ---------------------------------------------------------------------------

export function BenchmarkMonitor({
  benchmarkId,
  initialBenchmark,
  initialRuns,
  agents,
  loadError,
}: Readonly<{
  benchmarkId: string;
  initialBenchmark: Benchmark | null;
  initialRuns: { items: BenchmarkRun[]; next_cursor: string | null };
  agents: Agent[];
  loadError: boolean;
}>) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const cursor = cursors[cursors.length - 1];

  // Live run state maintained via WS deltas (or polling fallback).
  const [liveRuns, setLiveRuns] = useState<RunMap>(() =>
    runMapFromList(initialRuns.items),
  );
  const [liveBenchmark, setLiveBenchmark] = useState<Benchmark | null>(initialBenchmark);
  const [wsActive, setWsActive] = useState(false);
  const [pollingFallback, setPollingFallback] = useState(false);

  // RAF batching for WS deltas.
  const pendingDeltas = useRef<StreamMessage[]>([]);
  const rafHandle = useRef<number | null>(null);

  const flushDeltas = useCallback(() => {
    rafHandle.current = null;
    const msgs = pendingDeltas.current.splice(0);
    setLiveRuns((prev) => {
      let next = prev;
      for (const msg of msgs) {
        if (msg.type === "run_update") {
          next = mergeRunUpdate(next, msg);
        } else if (msg.type === "snapshot") {
          next = runMapFromList(msg.runs as unknown as BenchmarkRun[]);
        }
      }
      return next;
    });
    for (const msg of msgs) {
      if (msg.type === "snapshot") {
        setLiveBenchmark((prev) => ({
          ...(prev ?? {}),
          ...msg.benchmark,
          agent_ids: prev?.agent_ids ?? [],
          suite_id: prev?.suite_id ?? "",
          repetitions: prev?.repetitions ?? 1,
          seed: prev?.seed ?? 0,
        } as Benchmark));
      } else if (msg.type === "benchmark_complete") {
        setLiveBenchmark((prev) =>
          prev ? { ...prev, status: msg.benchmark_status } : prev,
        );
      }
    }
  }, []);

  const scheduleFlush = useCallback(
    (msg: StreamMessage) => {
      pendingDeltas.current.push(msg);
      if (rafHandle.current === null) {
        rafHandle.current = requestAnimationFrame(flushDeltas);
      }
    },
    [flushDeltas],
  );

  const terminal = isTerminal(liveBenchmark?.status ?? "");

  useRunStream({
    benchmarkId,
    onMessage: (msg) => {
      setWsActive(true);
      scheduleFlush(msg);
    },
    onFallback: () => {
      setWsActive(false);
      setPollingFallback(true);
    },
    terminal,
  });

  // Polling fallback (3 s, same as before — only active when WS fails twice).
  const query = useQuery({
    queryKey: ["benchmark", benchmarkId, cursor],
    queryFn: async () => {
      const suffix = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
      const response = await fetch(
        `/api/benchmarks/${encodeURIComponent(benchmarkId)}${suffix}`,
      );
      if (!response.ok) throw new Error("Benchmark status could not be refreshed");
      return (await response.json()) as Detail;
    },
    initialData:
      cursor === null && initialBenchmark
        ? { benchmark: initialBenchmark, runs: initialRuns }
        : undefined,
    enabled: pollingFallback || !wsActive,
    refetchInterval: (current) => {
      if (wsActive) return false;
      const status = current.state.data?.benchmark.status;
      return isTerminal(status ?? "") ? false : 3000;
    },
  });

  // Keep liveRuns in sync with polling data when WS is not active.
  useEffect(() => {
    if (wsActive || !query.data) return;
    setLiveRuns(runMapFromList(query.data.runs.items));
    setLiveBenchmark(query.data.benchmark);
  }, [wsActive, query.data]);

  const agentNames = useMemo(
    () => new Map(agents.map((a) => [a.id, a.name])),
    [agents],
  );

  const data = query.data;
  const summary = ((liveBenchmark?.summary ?? data?.benchmark.summary ?? {}) as Summary);
  const overview = summary.overall;
  const counts = summary.status_breakdown ?? {};

  const tasks = useMemo(
    () => Array.from(new Set(Array.from(liveRuns.values()).map((r) => r.task_id))).sort(),
    [liveRuns],
  );

  const totalCost = useMemo(
    () =>
      Array.from(liveRuns.values()).reduce(
        (sum, r) => sum + Number(r.cost_usd ?? 0),
        0,
      ),
    [liveRuns],
  );

  const eta = computeEta(liveRuns, liveBenchmark?.created_at ?? null);

  const percent = useMemo(() => {
    const total = Object.values(counts).reduce((s, v) => s + Number(v || 0), 0);
    const done =
      Number(counts.completed || 0) +
      Number(counts.agent_error || 0) +
      Number(counts.timeout || 0) +
      Number(counts.infra_error || 0);
    return total ? Math.round((done / total) * 100) : 0;
  }, [counts]);

  const benchmarkStatus = liveBenchmark?.status ?? data?.benchmark.status ?? "";
  const isComplete = isTerminal(benchmarkStatus);

  if (!liveBenchmark && !data && (loadError || query.isError)) {
    return (
      <div className="surface empty-state" role="alert">
        Benchmark data is unavailable. Check the ID or API connection.
      </div>
    );
  }

  const runsArray = Array.from(liveRuns.values());

  return (
    <>
      <div className="page-heading">
        <div>
          <Link
            className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-tan hover:text-paper"
            href="/"
          >
            <ArrowLeft size={14} />
            Leaderboard
          </Link>
          <p className="eyebrow">Benchmark run</p>
          <h1>Execution status</h1>
          <p className="page-subtitle mono">{benchmarkId}</p>
        </div>
        <div className="toolbar-group">
          {benchmarkStatus && (
            <Badge
              tone={
                benchmarkStatus === "completed"
                  ? "success"
                  : benchmarkStatus === "failed"
                    ? "danger"
                    : "info"
              }
            >
              {benchmarkStatus}
            </Badge>
          )}
          {wsActive && (
            <span className="text-xs text-teal-glow" aria-label="Live updates active">
              ● Live
            </span>
          )}
          <Button
            variant="outline"
            size="small"
            onClick={() => void query.refetch()}
            aria-label="Refresh benchmark status"
          >
            <RotateCw size={14} />
          </Button>
        </div>
      </div>

      {/* Summary tiles */}
      <div className="summary-grid" aria-label="Benchmark summary">
        <div className="summary-tile">
          <span>Success rate</span>
          <strong>
            {overview?.success_rate === undefined
              ? "—"
              : `${(overview.success_rate * 100).toFixed(1)}%`}
          </strong>
        </div>
        <div className="summary-tile">
          <span>Scored runs</span>
          <strong>{overview?.n ?? "—"}</strong>
        </div>
        <div className="summary-tile">
          <span>Running cost</span>
          <strong data-metric>{`$${totalCost.toFixed(3)}`}</strong>
        </div>
        <div className="summary-tile">
          <span>{isComplete ? "P95 latency" : "ETA"}</span>
          <strong>
            {isComplete
              ? overview?.duration_ms?.p95 === undefined
                ? "—"
                : `${(overview.duration_ms.p95 / 1000).toFixed(1)}s`
              : (eta ?? "—")}
          </strong>
        </div>
      </div>

      {/* Progress matrix */}
      {tasks.length > 0 && tasks.length <= 30 && (
        <section className="surface mb-5" aria-labelledby="matrix-title">
          <div className="surface-header">
            <div>
              <h2 className="section-title" id="matrix-title">
                Progress matrix
              </h2>
              <p className="section-note">
                {isComplete ? "All runs are terminal." : `${percent}% terminal`}
              </p>
            </div>
          </div>
          <div className="surface-body">
            <ProgressMatrix runs={liveRuns} agents={agentNames} tasks={tasks} />
          </div>
        </section>
      )}

      {/* Run status table */}
      <section className="surface" aria-labelledby="runs-title">
        <div className="surface-header">
          <div>
            <h2 className="section-title" id="runs-title">
              Run status
            </h2>
            <p className="section-note">
              {isComplete
                ? "All runs are terminal."
                : `${wsActive ? "Live updates" : "Refreshing every 3 seconds"} · ${percent}% terminal`}
            </p>
          </div>
          <Badge tone={isComplete ? "success" : "info"}>
            {isComplete ? "Complete" : "Live"}
          </Badge>
        </div>
        {runsArray.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Agent</th>
                  <th scope="col">Task</th>
                  <th scope="col">Attempt</th>
                  <th scope="col">Mode</th>
                  <th scope="col">Status</th>
                  <th scope="col">Duration</th>
                  <th scope="col">Cost</th>
                </tr>
              </thead>
              <tbody>
                {runsArray.map((run) => {
                  const statusEntry = getStatusEntry(run.status);
                  return (
                    <tr key={run.id}>
                      <td>{agentNames.get(run.agent_id) ?? run.agent_id.slice(0, 8)}</td>
                      <td className="mono">
                        <Link
                          className="text-teal-glow underline-offset-2 hover:underline"
                          href={`/runs/${run.id}`}
                        >
                          {run.task_id}
                        </Link>
                      </td>
                      <td>{run.attempt_no}</td>
                      <td>
                        <Badge tone={run.fault_mode === "faulted" ? "warning" : "neutral"}>
                          {run.fault_mode}
                        </Badge>
                      </td>
                      <td>
                        <span className="inline-flex items-center gap-1.5">
                          <statusEntry.icon size={13} aria-hidden="true" />
                          <Badge status={run.status}>{statusEntry.label}</Badge>
                        </span>
                      </td>
                      <td>
                        {run.duration_ms == null
                          ? "—"
                          : `${(run.duration_ms / 1000).toFixed(1)}s`}
                      </td>
                      <td>${Number(run.cost_usd || 0).toFixed(3)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            Runs will appear as soon as the benchmark is queued.
          </div>
        )}
        {/* Pagination (polling mode only) */}
        {!wsActive && (
          <div className="surface-header border-t-0 border-b-0">
            <Button
              variant="outline"
              size="small"
              disabled={cursors.length < 2}
              onClick={() => setCursors((v) => v.slice(0, -1))}
            >
              Previous
            </Button>
            <span className="stepper">Page {cursors.length}</span>
            <Button
              variant="outline"
              size="small"
              disabled={!data?.runs.next_cursor}
              onClick={() =>
                data?.runs.next_cursor &&
                setCursors((v) => [...v, data.runs.next_cursor!])
              }
            >
              Next
            </Button>
          </div>
        )}
      </section>
    </>
  );
}
