"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, LoaderCircle } from "lucide-react";
import { PayloadView } from "@/components/payload-view";
import type { StepDetail, StepSummary } from "@/lib/api-server";

function hasValue(value: unknown): boolean {
  return value !== undefined && value !== null && value !== "";
}

export function StepPayloadDetail({ runId, step }: Readonly<{ runId: string; step: StepSummary }>) {
  const query = useQuery({
    queryKey: ["run-step-detail", runId, step.seq],
    queryFn: async () => {
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/steps/${step.seq}`);
      if (!response.ok) throw new Error("Step payload is unavailable");
      return (await response.json()) as StepDetail;
    },
  });
  if (query.isPending) return <p className="payload-loading"><LoaderCircle size={14} className="animate-spin" />Loading event payload</p>;
  if (query.isError || !query.data) return <p className="payload-error" role="status"><AlertCircle size={14} />Could not load this event payload.</p>;

  const payload = query.data.payload;
  const usage = payload.usage && typeof payload.usage === "object" ? payload.usage as Record<string, unknown> : {};
  const prompt = payload.prompt ?? payload.messages;
  const response = payload.response ?? payload.output ?? payload.content;
  return (
    <div className="step-payload">
      {step.truncated && <p className="payload-truncated" role="note">This event was truncated at the platform payload limit.</p>}
      {step.type === "llm" && (
        <>
          <dl className="payload-facts">
            <div><dt>Model</dt><dd>{String(payload.model ?? "Unknown")}</dd></div>
            <div><dt>Input tokens</dt><dd>{String(usage.prompt_tokens ?? usage.input_tokens ?? "—")}</dd></div>
            <div><dt>Output tokens</dt><dd>{String(usage.completion_tokens ?? usage.output_tokens ?? "—")}</dd></div>
            <div><dt>Latency</dt><dd>{(step.duration_ms / 1000).toFixed(2)}s</dd></div>
          </dl>
          {hasValue(prompt) && <PayloadSection title="Prompt" value={prompt} />}
          {hasValue(response) && <PayloadSection title="Response" value={response} />}
        </>
      )}
      {step.type === "tool" && (
        <>
          <dl className="payload-facts">
            <div><dt>Tool</dt><dd>{String(payload.name ?? step.short_label)}</dd></div>
            <div><dt>Outcome</dt><dd>{step.ok ? "Completed" : "Error"}</dd></div>
          </dl>
          {hasValue(payload.arguments ?? payload.args) && <PayloadSection title="Arguments" value={payload.arguments ?? payload.args} />}
          {hasValue(payload.result) && <PayloadSection title="Result" value={payload.result} />}
          {hasValue(payload.error ?? payload.error_type) && <PayloadSection title="Error" value={payload.error ?? payload.error_type} />}
        </>
      )}
      {step.type === "retry" && (
        <dl className="payload-facts">
          <div><dt>Attempt</dt><dd>{String(payload.attempt ?? "—")}</dd></div>
          <div><dt>Reason</dt><dd>{String(payload.reason ?? payload.status_code ?? "Retry requested")}</dd></div>
          <div><dt>Backoff</dt><dd>{String(payload.backoff_s ?? payload.backoff_ms ?? "—")}</dd></div>
        </dl>
      )}
      <details className="raw-event">
        <summary>Full event payload</summary>
        <PayloadView value={payload} />
      </details>
    </div>
  );
}

function PayloadSection({ title, value }: Readonly<{ title: string; value: unknown }>) {
  return <section className="payload-section"><h4>{title}</h4><PayloadView value={value} /></section>;
}