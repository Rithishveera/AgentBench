import { AppShell } from "@/components/app-shell";
import { BenchmarkWizard } from "@/components/benchmark-wizard";
import { allAgents, apiClient, type Agent, type Suite } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function NewBenchmarkPage() {
  let agents: Agent[] = [];
  let suites: Suite[] = [];
  let loadError = false;
  try {
    const [agentRows, suiteResult] = await Promise.all([
      allAgents(),
      apiClient().GET("/suites"),
    ]);
    agents = agentRows;
    if (suiteResult.data) suites = suiteResult.data as Suite[];
    else loadError = true;
  } catch {
    loadError = true;
  }
  return (
    <AppShell active="/benchmarks/new">
      <BenchmarkWizard agents={agents} suites={suites} loadError={loadError} />
    </AppShell>
  );
}