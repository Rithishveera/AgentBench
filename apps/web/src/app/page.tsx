import { AppShell } from "@/components/app-shell";
import { Leaderboard } from "@/components/leaderboard";
import { apiClient, type Agent, type LeaderboardItem } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let items: LeaderboardItem[] = [];
  let agents: Agent[] = [];
  let error = false;
  try {
    const client = apiClient();
    const [leaderboardResult, agentResult] = await Promise.allSettled([
      client.GET("/results/leaderboard"),
      client.GET("/agents", { params: { query: { limit: 100 } } }),
    ]);
    if (leaderboardResult.status === "fulfilled" && leaderboardResult.value.data) {
      items = (leaderboardResult.value.data as { items: LeaderboardItem[] }).items;
    } else {
      error = true;
    }
    if (agentResult.status === "fulfilled" && agentResult.value.data) {
      agents = (agentResult.value.data as { items: Agent[] }).items;
    }
  } catch {
    error = true;
  }
  return (
    <AppShell active="/">
      <Leaderboard initialItems={items} agents={agents} initialError={error} />
    </AppShell>
  );
}