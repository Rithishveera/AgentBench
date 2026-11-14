import { AppShell } from "@/components/app-shell";
import { RunHeader } from "@/components/run-header";
import { RunTimelineIsland } from "@/components/run-timeline-island";
import { RunVerdictPanel } from "@/components/run-verdict-panel";
import { allAgents, apiClient, type Agent, type CursorPage, type FaultRecord, type RunRecord, type StepSummary } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function RunPage({
  params,
}: Readonly<{ params: Promise<{ runId: string }> }>) {
  const { runId } = await params;
  let run: RunRecord | null = null;
  let initialSteps: CursorPage<StepSummary> | null = null;
  let initialFaults: CursorPage<FaultRecord> | null = null;
  let agents: Agent[] = [];
  try {
    const client = apiClient();
    const [runResult, stepsResult, faultsResult, agentRows] = await Promise.allSettled([
      client.GET("/runs/{run_id}", { params: { path: { run_id: runId } } }),
      client.GET("/runs/{run_id}/steps", { params: { path: { run_id: runId }, query: { after_seq: -1, limit: 100 } } }),
      client.GET("/runs/{run_id}/faults", { params: { path: { run_id: runId }, query: { after_seq: -1, limit: 100 } } }),
      allAgents(),
    ]);
    if (runResult.status === "fulfilled" && runResult.value.response.ok && runResult.value.data) {
      run = runResult.value.data as RunRecord;
    }
    if (stepsResult.status === "fulfilled" && stepsResult.value.data) {
      initialSteps = stepsResult.value.data as CursorPage<StepSummary>;
    }
    if (faultsResult.status === "fulfilled" && faultsResult.value.data) {
      initialFaults = faultsResult.value.data as CursorPage<FaultRecord>;
    }
    if (agentRows.status === "fulfilled") agents = agentRows.value;
  } catch {
    run = null;
  }

  if (!run) {
    return <AppShell active=""><div className="surface empty-state" role="alert">Run details are unavailable. Check the run ID or API connection.</div></AppShell>;
  }
  const agentName = agents.find((agent) => agent.id === run?.agent_id)?.name ?? `Agent ${run.agent_id.slice(0, 8)}`;
  return (
    <AppShell active="">
      <RunHeader run={run} agentName={agentName} initialFaults={initialFaults} />
      <RunTimelineIsland run={{ ...run, artifact: null }} initialSteps={initialSteps} initialFaults={initialFaults} />
      <RunVerdictPanel verdict={run.verdict} artifact={run.artifact} error={run.error} />
    </AppShell>
  );
}