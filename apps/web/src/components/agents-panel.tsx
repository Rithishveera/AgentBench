"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Plus, RotateCw } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { Agent, AgentPage } from "@/lib/api-server";
import { registerAgentSchema } from "@/lib/validation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getStatusEntry } from "@/lib/status";

function health(agent: Agent): { text: string; tone: "neutral" | "success" | "warning" | "danger" | "info" } {
  if (!agent.last_health_check_at) return { text: "Unverified", tone: "neutral" };
  const age = Date.now() - new Date(agent.last_health_check_at).getTime();
  return age < 5 * 60_000
    ? { text: "Healthy · checked", tone: "success" }
    : { text: "Check stale", tone: "warning" };
}

export function AgentsPanel({
  initialPage,
  initialError,
}: Readonly<{ initialPage: AgentPage; initialError: boolean }>) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const cursor = cursors[cursors.length - 1];
  const [formError, setFormError] = useState("");
  const [secret, setSecret] = useState("");
  const [copied, setCopied] = useState(false);
  const queryClient = useQueryClient();
  const pageQuery = useQuery({
    queryKey: ["agents", cursor],
    queryFn: async () => {
      const suffix = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
      const response = await fetch(`/api/agents${suffix}`);
      if (!response.ok) throw new Error("Agent directory is unavailable");
      return (await response.json()) as AgentPage;
    },
    initialData: cursor === null && !initialError ? initialPage : undefined,
  });
  const registration = useMutation({
    mutationFn: async (body: unknown) => {
      const response = await fetch("/api/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await response.json()) as Agent & { secret?: string; detail?: string };
      if (!response.ok) throw new Error(data.detail ?? "Agent registration failed.");
      return data;
    },
    onSuccess: (agent) => {
      setSecret(agent.secret ?? "");
      setCopied(false);
      setFormError("");
      setCursors([null]);
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const parsed = registerAgentSchema.safeParse({
      name: form.get("name"),
      url: form.get("url"),
      category: form.get("category"),
      framework_tag: form.get("framework_tag") || undefined,
      max_concurrency: Number(form.get("max_concurrency")),
    });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Check the agent details.");
      return;
    }
    setFormError("");
    registration.mutate(parsed.data);
    event.currentTarget.reset();
  }

  async function copySecret() {
    await navigator.clipboard.writeText(secret);
    setCopied(true);
  }

  const agents = pageQuery.data?.items ?? [];
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Connected systems</p>
          <h1>Agents</h1>
          <p className="page-subtitle">Register external HTTP agents and manage benchmark access.</p>
        </div>
        <Badge tone="info">{agents.length} on this page</Badge>
      </div>

      {secret && (
        <section className="surface mb-5" aria-labelledby="secret-title">
          <div className="surface-header">
            <h2 className="section-title" id="secret-title">Registration secret</h2>
            <Button variant="quiet" size="small" onClick={() => setSecret("")}>Dismiss</Button>
          </div>
          <div className="surface-body grid gap-3">
            <div className="notice"><strong>Copy this secret now.</strong> It is shown only once and cannot be retrieved later.</div>
            <div className="toolbar">
              <code className="secret-box flex-1">{secret}</code>
              <Button variant="outline" onClick={copySecret} aria-label="Copy registration secret">
                {copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>
        </section>
      )}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,.8fr)]">
        <section className="surface" aria-labelledby="directory-title">
          <div className="surface-header">
            <div>
              <h2 className="section-title" id="directory-title">Directory</h2>
              <p className="section-note">Health reflects the registration-time check.</p>
            </div>
            <Button variant="quiet" size="small" onClick={() => void pageQuery.refetch()} aria-label="Refresh agent directory"><RotateCw size={14} /></Button>
          </div>
          {initialError && !agents.length ? (
            <div className="empty-state" role="status">The API is not reachable yet.</div>
          ) : pageQuery.isError ? (
            <div className="empty-state" role="alert">Could not load this page of agents.</div>
          ) : agents.length === 0 ? (
            <div className="empty-state">No agents registered yet.</div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th scope="col">Agent</th><th scope="col">Category</th><th scope="col">Health</th><th scope="col">Concurrency</th></tr></thead>
                <tbody>
                  {agents.map((agent) => {
                    const state = health(agent);
                    return (
                      <tr key={agent.id}>
                        <td>
                          <span className="metric-main">{agent.name}</span>
                          <span className="metric-sub">{agent.framework_tag || "Framework not specified"} · <span className="mono">{agent.url}</span></span>
                        </td>
                        <td>{agent.category}</td>
                        <td><Badge tone={state.tone} title={agent.last_health_check_at ?? undefined}>{state.text}</Badge></td>
                        <td>{agent.max_concurrency}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <div className="surface-header border-t-0 border-b-0">
            <Button variant="outline" size="small" disabled={cursors.length < 2} onClick={() => setCursors((value) => value.slice(0, -1))}>Previous</Button>
            <span className="stepper">Page {cursors.length}</span>
            <Button variant="outline" size="small" disabled={!pageQuery.data?.next_cursor} onClick={() => pageQuery.data?.next_cursor && setCursors((value) => [...value, pageQuery.data!.next_cursor])}>Next</Button>
          </div>
        </section>

        <section className="surface" aria-labelledby="register-title">
          <div className="surface-header">
            <div><h2 className="section-title" id="register-title">Register an agent</h2><p className="section-note">The API checks /health before saving.</p></div>
            <Plus size={17} className="text-teal-glow" aria-hidden="true" />
          </div>
          <form className="surface-body grid gap-4" onSubmit={submit}>
            <label className="control-label">Display name<Input name="name" required maxLength={200} placeholder="e.g. PatchPilot" /></label>
            <label className="control-label">Agent base URL<Input name="url" type="url" required placeholder="https://agent.example.com" /></label>
            <label className="control-label">Category
              <select className="control h-10 rounded-md border border-tan bg-ink-raised px-3 text-sm text-paper" name="category" required defaultValue="coding">
                <option value="coding">Coding</option><option value="research">Research</option><option value="support">Support</option>
              </select>
            </label>
            <label className="control-label">Framework tag<Input name="framework_tag" maxLength={100} placeholder="Optional" /></label>
            <label className="control-label">Max concurrent runs<Input name="max_concurrency" type="number" min={1} max={100} defaultValue={2} required /></label>
            {(formError || registration.error) && <p className="error-text" role="alert">{formError || registration.error?.message}</p>}
            <Button type="submit" disabled={registration.isPending}>{registration.isPending ? "Checking agent…" : "Register agent"}</Button>
          </form>
        </section>
      </div>
    </>
  );
}
