import "server-only";

import createClient from "openapi-fetch";
import type { paths } from "@/lib/api-schema";

export function apiClient() {
  const baseUrl = process.env.AGENTBENCH_API_URL;
  const apiKey = process.env.API_KEY;
  if (!baseUrl || !apiKey) {
    throw new Error("AGENTBENCH_API_URL and API_KEY must be configured on the server");
  }
  return createClient<paths>({
    baseUrl,
    headers: { "X-API-Key": apiKey },
    fetch: (request) => fetch(new Request(request, { cache: "no-store" })),
  });
}

export async function allAgents() {
  const client = apiClient();
  const agents: Agent[] = [];
  let cursor: string | undefined;
  do {
    const result = await client.GET("/agents", {
      params: { query: { limit: 100, ...(cursor ? { cursor } : {}) } },
    });
    if (!result.response.ok || !result.data) {
      throw new Error("Agent directory is unavailable");
    }
    const page = result.data as AgentPage;
    agents.push(...page.items);
    cursor = page.next_cursor ?? undefined;
  } while (cursor);
  return agents;
}

export type Agent = {
  id: string;
  name: string;
  url: string;
  category: string;
  framework_tag: string | null;
  max_concurrency: number;
  created_at: string;
  last_health_check_at: string | null;
};

export type AgentPage = { items: Agent[]; next_cursor: string | null };
export type Suite = { id: string; title: string; task_count: number };
export type TaskSummary = {
  id: string;
  title: string;
  category: string;
  limits: { timeout_s: number; max_steps: number; max_cost_usd: number };
  digest: string;
};
export type LeaderboardItem = {
  agent_id: string;
  benchmark_id: string;
  created_at: string;
  success_rate: number;
  ci: [number, number];
  n: number;
  summary: Record<string, unknown>;
};
export type Benchmark = {
  id: string;
  status: string;
  suite_id: string;
  repetitions: number;
  agent_ids: string[];
  summary: Record<string, unknown> | null;
  seed: number;
  created_at: string;
  finished_at: string | null;
};
export type BenchmarkRun = {
  id: string;
  agent_id: string;
  task_id: string;
  attempt_no: number;
  fault_mode: "none" | "faulted";
  status: string;
  verdict: { passed?: boolean } | null;
  failure_cause: string | null;
  duration_ms: number | null;
  cost_usd: number | string;
  started_at: string | null;
  finished_at: string | null;
};