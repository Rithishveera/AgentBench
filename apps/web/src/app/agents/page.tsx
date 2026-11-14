import { AppShell } from "@/components/app-shell";
import { AgentsPanel } from "@/components/agents-panel";
import { apiClient, type Agent, type AgentPage } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  let initialPage: AgentPage = { items: [], next_cursor: null };
  let initialError = false;
  try {
    const result = await apiClient().GET("/agents", { params: { query: { limit: 50 } } });
    if (result.data) initialPage = result.data as AgentPage;
    else initialError = true;
  } catch {
    initialError = true;
  }
  return (
    <AppShell active="/agents">
      <AgentsPanel initialPage={initialPage} initialError={initialError} />
    </AppShell>
  );
}