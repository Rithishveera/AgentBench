import { AppShell } from "@/components/app-shell";
import { BenchmarkMonitor } from "@/components/benchmark-monitor";
import { allAgents, apiClient, type Agent, type Benchmark, type BenchmarkRun } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function BenchmarkPage({
  params,
}: Readonly<{ params: Promise<{ benchmarkId: string }> }>) {
  const { benchmarkId } = await params;
  let benchmark: Benchmark | null = null;
  let runs: { items: BenchmarkRun[]; next_cursor: string | null } = { items: [], next_cursor: null };
  let agents: Agent[] = [];
  let loadError = false;
  try {
    const client = apiClient();
    const [benchmarkResult, runResult, agentRows] = await Promise.all([
      client.GET("/benchmarks/{benchmark_id}", { params: { path: { benchmark_id: benchmarkId } } }),
      client.GET("/benchmarks/{benchmark_id}/runs", { params: { path: { benchmark_id: benchmarkId }, query: { limit: 100 } } }),
      allAgents(),
    ]);
    if (benchmarkResult.data) benchmark = benchmarkResult.data as Benchmark;
    else loadError = true;
    if (runResult.data) runs = runResult.data as typeof runs;
    else loadError = true;
    agents = agentRows;
  } catch {
    loadError = true;
  }
  return (
    <AppShell active="/benchmarks/new">
      <BenchmarkMonitor benchmarkId={benchmarkId} initialBenchmark={benchmark} initialRuns={runs} agents={agents} loadError={loadError} />
    </AppShell>
  );
}