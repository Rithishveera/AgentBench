"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, FlaskConical } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Agent, AgentPage, Suite, TaskSummary } from "@/lib/api-server";
import { benchmarkRequestSchema } from "@/lib/validation";

type FaultName = "rate_limit_429" | "latency_spike" | "empty_response" | "error_5xx";
const faultOptions: { key: FaultName; label: string; detail: string }[] = [
  { key: "rate_limit_429", label: "Rate limit (429)", detail: "Reject one LLM call with a retryable rate limit." },
  { key: "latency_spike", label: "Latency spike", detail: "Delay one response by the configured duration." },
  { key: "empty_response", label: "Empty response", detail: "Return an empty assistant message once." },
  { key: "error_5xx", label: "Server error (5xx)", detail: "Fail one LLM call with a server error." },
];

export function BenchmarkWizard({
  agents,
  suites,
  loadError,
}: Readonly<{ agents: Agent[]; suites: Suite[]; loadError: boolean }>) {
  const [suiteId, setSuiteId] = useState("");
  const [agentIds, setAgentIds] = useState<string[]>([]);
  const [repetitions, setRepetitions] = useState(1);
  const [paired, setPaired] = useState(false);
  const [latencySeconds, setLatencySeconds] = useState(2.5);
  const [faults, setFaults] = useState<Record<FaultName, boolean>>({
    rate_limit_429: false,
    latency_spike: false,
    empty_response: false,
    error_5xx: false,
  });
  const [validationError, setValidationError] = useState("");
  const suitesQuery = useQuery({
    queryKey: ["suites"],
    queryFn: async () => {
      const response = await fetch("/api/suites");
      if (!response.ok) throw new Error("Suites are unavailable");
      return (await response.json()) as Suite[];
    },
    initialData: loadError ? undefined : suites,
  });
  const agentsQuery = useQuery({
    queryKey: ["benchmark-agents"],
    queryFn: async () => {
      const response = await fetch("/api/agents?limit=100");
      if (!response.ok) throw new Error("Agent directory is unavailable");
      return (await response.json()) as AgentPage;
    },
    initialData: loadError ? undefined : { items: agents, next_cursor: null },
  });
  const tasksQuery = useQuery({
    queryKey: ["suite-tasks", suiteId],
    enabled: Boolean(suiteId),
    queryFn: async () => {
      const response = await fetch(`/api/suites/${encodeURIComponent(suiteId)}/tasks`);
      if (!response.ok) throw new Error("Task limits are unavailable");
      return (await response.json()) as TaskSummary[];
    },
  });
  const create = useMutation({
    mutationFn: async (body: unknown) => {
      const response = await fetch("/api/benchmarks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = (await response.json()) as { id?: string; detail?: string };
      if (!response.ok || !result.id) throw new Error(result.detail ?? "Benchmark could not be created.");
      return result.id;
    },
    onSuccess: (id) => window.location.assign(`/benchmarks/${id}`),
  });
  const tasks = tasksQuery.data ?? [];
  const availableSuites = suitesQuery.data ?? [];
  const availableAgents = agentsQuery.data?.items ?? [];
  const selectedAgents = availableAgents.filter((agent) => agentIds.includes(agent.id));
  const hasFault = Object.values(faults).some(Boolean);
  const taskBudget = tasks.reduce((sum, task) => sum + task.limits.max_cost_usd, 0);
  const estimatedCost = taskBudget * repetitions * selectedAgents.length * (paired ? 2 : 1);
  const estimatedRuns = tasks.length * repetitions * selectedAgents.length * (paired ? 2 : 1);

  function toggleAgent(id: string) {
    setAgentIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const faultFlags: Record<string, unknown> = {};
    if (faults.rate_limit_429) faultFlags.rate_limit_429 = { count: 1 };
    if (faults.latency_spike) faultFlags.latency_spike = latencySeconds;
    if (faults.empty_response) faultFlags.empty_response = 1;
    if (faults.error_5xx) faultFlags.error_5xx = 1;
    const parsed = benchmarkRequestSchema.safeParse({
      suite_id: suiteId,
      agent_ids: agentIds,
      repetitions,
      fault_flags: faultFlags,
      paired,
    });
    if (!parsed.success) {
      setValidationError(parsed.error.issues[0]?.message ?? "Check benchmark settings.");
      return;
    }
    setValidationError("");
    create.mutate(parsed.data);
  }

  return (
    <>
      <div className="page-heading">
        <div><p className="eyebrow">Evaluation setup</p><h1>New benchmark</h1><p className="page-subtitle">Choose a task suite, agents, and controlled fault conditions.</p></div>
        <Badge tone="info"><FlaskConical size={13} className="mr-1" />{estimatedRuns} planned runs</Badge>
      </div>
      {loadError && <p className="notice mb-4" role="status">Some setup data could not be loaded. Refresh when the API is ready.</p>}
      <form className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(300px,.7fr)]" onSubmit={submit}>
        <div className="grid gap-5">
          <section className="surface" aria-labelledby="scope-title">
            <div className="surface-header"><div><h2 className="section-title" id="scope-title">1. Evaluation scope</h2><p className="section-note">Visible fixtures only are sent to agents.</p></div></div>
            <div className="surface-body grid gap-5">
              <label className="control-label">Task suite
                <select className="control h-10 rounded-md border border-tan bg-ink-raised px-3 text-sm text-paper" value={suiteId} onChange={(event) => setSuiteId(event.target.value)} required>
                  <option value="">Select a suite</option>
                  {availableSuites.map((suite) => <option key={suite.id} value={suite.id}>{suite.title} · {suite.task_count} tasks</option>)}
                </select>
              </label>
              {tasksQuery.isError && <p className="error-text" role="alert">Could not load task limits for this suite.</p>}
              <fieldset className="grid gap-3 border-0 p-0">
                <legend className="control-label mb-1">Agents <span className="font-normal text-tan">Select one or more</span></legend>
                {availableAgents.length === 0 ? <p className="text-xs text-tan">Register an agent before creating a benchmark.</p> : availableAgents.map((agent) => (
                  <label className="checkbox-row rounded-md border border-tan p-3" key={agent.id}>
                    <input type="checkbox" checked={agentIds.includes(agent.id)} onChange={() => toggleAgent(agent.id)} />
                    <span className="checkbox-copy"><strong>{agent.name}</strong><span>{agent.category} · {agent.framework_tag || "No framework tag"}</span></span>
                  </label>
                ))}
              </fieldset>
              <label className="control-label max-w-48">Repetitions per task<Input type="number" min={1} max={1000} value={repetitions} onChange={(event) => setRepetitions(Number(event.target.value))} /></label>
            </div>
          </section>

          <section className="surface" aria-labelledby="fault-title">
            <div className="surface-header"><div><h2 className="section-title" id="fault-title">2. Resilience conditions</h2><p className="section-note">Faults are deterministic for each benchmark run.</p></div></div>
            <div className="surface-body grid gap-3">
              {faultOptions.map((fault) => (
                <label className="checkbox-row rounded-md border border-tan p-3" key={fault.key}>
                  <input type="checkbox" checked={faults[fault.key]} onChange={(event) => setFaults((current) => ({ ...current, [fault.key]: event.target.checked }))} />
                  <span className="checkbox-copy"><strong>{fault.label}</strong><span>{fault.detail}</span></span>
                </label>
              ))}
              {faults.latency_spike && <label className="control-label max-w-48">Added latency (seconds)<Input type="number" min={0.1} max={60} step={0.1} value={latencySeconds} onChange={(event) => setLatencySeconds(Number(event.target.value))} /></label>}
              <label className="checkbox-row border-t border-tan pt-4">
                <input type="checkbox" checked={paired} disabled={!hasFault} onChange={(event) => setPaired(event.target.checked)} />
                <span className="checkbox-copy"><strong>Paired baseline and faulted runs</strong><span>{hasFault ? "Runs each selection once without faults and once with the selected faults." : "Select an injected fault to enable paired runs."}</span></span>
              </label>
            </div>
          </section>
        </div>

        <aside className="surface xl:sticky xl:top-5" aria-labelledby="estimate-title">
          <div className="surface-header"><div><h2 className="section-title" id="estimate-title">Worst-case budget</h2><p className="section-note">Based on every task configured max cost.</p></div></div>
          <div className="surface-body grid gap-4">
            <div className="summary-tile"><span>Estimated ceiling</span><strong>${estimatedCost.toFixed(2)}</strong></div>
            <dl className="grid gap-2 text-xs text-tan">
              <div className="flex justify-between gap-3"><dt>Tasks</dt><dd className="m-0 font-semibold text-paper">{tasks.length || "—"}</dd></div>
              <div className="flex justify-between gap-3"><dt>Agents</dt><dd className="m-0 font-semibold text-paper">{selectedAgents.length}</dd></div>
              <div className="flex justify-between gap-3"><dt>Repetitions</dt><dd className="m-0 font-semibold text-paper">{repetitions}</dd></div>
              <div className="flex justify-between gap-3"><dt>Run variants</dt><dd className="m-0 font-semibold text-paper">{paired ? "Baseline + faulted" : "Single"}</dd></div>
            </dl>
            <p className="notice"><AlertTriangle size={14} className="mr-1 inline" aria-hidden="true" />Estimate assumes every run spends its full task budget; actual usage is usually lower.</p>
            {(validationError || create.error) && <p className="error-text" role="alert">{validationError || create.error?.message}</p>}
            <Button type="submit" disabled={create.isPending || !tasks.length || !selectedAgents.length}>
              {create.isPending ? "Queueing benchmark…" : "Create benchmark"}<ArrowRight size={15} aria-hidden="true" />
            </Button>
          </div>
        </aside>
      </form>
    </>
  );
}
