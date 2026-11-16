"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, Plus } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Agent, LeaderboardItem } from "@/lib/api-server";

type LeaderboardPayload = { items: LeaderboardItem[] };
type MetricSummary = {
  pass_at_k?: { k?: number; value?: number; n?: number; excluded?: number };
  duration_ms?: { p95?: number };
  cost_per_success_usd?: number;
  resilience?: number;
};
type SortKey = "success" | "pass" | "latency" | "cost" | "resilience" | "n";

const columns: { key: SortKey; label: string }[] = [
  { key: "success", label: "Success rate" },
  { key: "pass", label: "Pass^k" },
  { key: "latency", label: "P95 latency" },
  { key: "cost", label: "Cost / success" },
  { key: "resilience", label: "Resilience" },
  { key: "n", label: "N" },
];

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function Leaderboard({
  initialItems,
  agents,
  initialError,
}: Readonly<{
  initialItems: LeaderboardItem[];
  agents: Agent[];
  initialError: boolean;
}>) {
  const [category, setCategory] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("success");
  const [descending, setDescending] = useState(true);
  const query = useQuery({
    queryKey: ["leaderboard", category],
    queryFn: async () => {
      const suffix = category === "all" ? "" : `?category=${encodeURIComponent(category)}`;
      const response = await fetch(`/api/results/leaderboard${suffix}`);
      if (!response.ok) throw new Error("Leaderboard is unavailable");
      return (await response.json()) as LeaderboardPayload;
    },
    initialData: category === "all" && !initialError ? { items: initialItems } : undefined,
  });
  const agentNames = useMemo(
    () => new Map(agents.map((agent) => [agent.id, agent.name])),
    [agents],
  );
  const rows = useMemo(() => {
    const value = (row: LeaderboardItem) => {
      const summary = row.summary as MetricSummary;
      switch (sortKey) {
        case "success": return row.success_rate;
        case "pass": return summary.pass_at_k?.value ?? -1;
        case "latency": return summary.duration_ms?.p95 ?? -1;
        case "cost": return summary.cost_per_success_usd ?? -1;
        case "resilience": return summary.resilience ?? -1;
        case "n": return row.n;
      }
    };
    return [...(query.data?.items ?? [])].sort((a, b) => {
      const delta = Number(value(a)) - Number(value(b));
      return (descending ? -1 : 1) * (delta || a.agent_id.localeCompare(b.agent_id));
    });
  }, [descending, query.data?.items, sortKey]);

  function sortBy(key: SortKey) {
    if (sortKey === key) setDescending((value) => !value);
    else {
      setSortKey(key);
      setDescending(true);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Performance index</p>
          <h1>Agent leaderboard</h1>
          <p className="page-subtitle">Latest completed benchmark per agent, with uncertainty kept in view.</p>
        </div>
        <Link
          className="inline-flex min-h-10 items-center justify-center gap-2 rounded-pill bg-red px-4 text-sm font-semibold text-paper transition-colors hover:bg-red/80"
          href="/benchmarks/new"
        >
          <Plus size={16} aria-hidden="true" />Run benchmark
        </Link>
      </div>

      <section className="surface" aria-labelledby="leaderboard-title">
        <div className="surface-header">
          <div>
            <h2 className="section-title" id="leaderboard-title">Latest results</h2>
            <p className="section-note">Aggregates exclude infrastructure errors.</p>
          </div>
          <label className="toolbar-group text-xs font-semibold text-tan">
            Category
            <span className="relative">
              <select
                aria-label="Filter by category"
                className="control h-9 appearance-none rounded-md border border-tan bg-ink-raised py-1 pl-3 pr-8 text-xs text-paper"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              >
                <option value="all">All categories</option>
                <option value="coding">Coding</option>
                <option value="research">Research</option>
                <option value="support">Support</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-tan" size={14} aria-hidden="true" />
            </span>
          </label>
        </div>
        {initialError && !query.data?.items.length ? (
          <div className="empty-state" role="status">The API is not reachable yet. Start the platform services to load results.</div>
        ) : query.isError ? (
          <div className="empty-state" role="alert">Could not refresh leaderboard data. Existing results remain visible.</div>
        ) : rows.length === 0 ? (
          <div className="empty-state">No completed benchmarks match this category yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Agent</th>
                  {columns.map(({ key, label }) => (
                    <th key={key} scope="col" aria-sort={sortKey === key ? (descending ? "descending" : "ascending") : "none"}>
                      <button className="inline-flex items-center gap-1 text-tan hover:text-paper" onClick={() => sortBy(key)}>
                        {label}
                        {sortKey !== key ? <ArrowUpDown size={12} aria-hidden="true" /> : descending ? <ArrowDown size={12} aria-hidden="true" /> : <ArrowUp size={12} aria-hidden="true" />}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const summary = row.summary as MetricSummary;
                  const pass = summary.pass_at_k;
                  return (
                    <tr key={row.agent_id}>
                      <td>
                        <span className="metric-main">{agentNames.get(row.agent_id) ?? `Agent ${row.agent_id.slice(0, 8)}`}</span>
                        <span className="metric-sub">{row.agent_id.slice(0, 13)} · {new Date(row.created_at).toLocaleDateString()}</span>
                      </td>
                      <td>
                        <span className="metric-main">{formatPercent(row.success_rate)}</span>
                        <span className="metric-sub">95% CI {formatPercent(row.ci[0])}–{formatPercent(row.ci[1])}</span>
                      </td>
                      <td>{pass?.value === undefined ? <span className="text-tan">Not reported</span> : <><span className="metric-main">{formatPercent(pass.value)}</span><span className="metric-sub">k={pass.k} · {pass.n} tasks · {pass.excluded} excluded</span></>}</td>
                      <td><span className="metric-main">{summary.duration_ms?.p95 === undefined ? "—" : `${(summary.duration_ms.p95 / 1000).toFixed(1)}s`}</span></td>
                      <td><span className="metric-main">{summary.cost_per_success_usd === undefined ? "—" : `$${summary.cost_per_success_usd.toFixed(3)}`}</span></td>
                      <td><span className="metric-main">{summary.resilience === undefined ? "—" : formatPercent(summary.resilience)}</span></td>
                      <td>{row.n < 30 ? <Badge tone="warning" title="Small sample: estimates may be unstable">{row.n} · low sample</Badge> : <span className="metric-main">{row.n}</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
