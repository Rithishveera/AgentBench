import type { RunVerdict } from "@/lib/api-server";
import { StampBadge } from "@/components/ui/stamp-badge";

function artifactText(artifact: Record<string, unknown> | null) {
  const patch = artifact?.patch;
  return typeof patch === "string" ? patch : null;
}

export function RunVerdictPanel({
  verdict,
  artifact,
  error,
}: Readonly<{
  verdict: RunVerdict | null;
  artifact: Record<string, unknown> | null;
  error: string | null;
}>) {
  const details = verdict?.details ?? {};
  const failures = Array.isArray(details.failed_tests)
    ? details.failed_tests.filter((value): value is string => typeof value === "string")
    : [];
  const reason = typeof details.reason === "string" ? details.reason : error;
  const patch = artifactText(artifact);
  const answer = typeof artifact?.answer === "string" ? artifact.answer : null;

  return (
    <section className="surface verdict-panel" aria-labelledby="verdict-heading">
      <div className="surface-header">
        <div>
          <h2 className="section-title" id="verdict-heading">Validator details</h2>
          <p className="section-note">
            {verdict ? `${verdict.error_kind} · score ${(verdict.score * 100).toFixed(0)}%` : error || "No verdict was recorded."}
          </p>
        </div>
        {verdict && (
          <StampBadge verdict={verdict.passed ? "Passed" : "Failed"} />
        )}
      </div>
      <div className="surface-body grid gap-4">
        {reason && <p className="verdict-reason">{reason}</p>}
        {failures.length > 0 && (
          <div>
            <h3 className="section-title mb-2">Failing tests</h3>
            <ul className="failure-list">
              {failures.map((name, index) => <li className="mono" key={`${name}-${index}`}>{name}</li>)}
            </ul>
          </div>
        )}
        {patch && (
          <details className="patch-details">
            <summary>Submitted patch</summary>
            <pre className="patch-pre"><code>{patch.split("\n").map((line, index) => {
              const cls = line.startsWith("+") ? "diff-add" : line.startsWith("-") ? "diff-remove" : line.startsWith("@@") ? "diff-hunk" : "";
              // gutter symbol conveyed by the line content itself (+/- prefix) — color is not the sole signal
              return <span className={cls} key={index}>{line || " "}{"\n"}</span>;
            })}</code></pre>
          </details>
        )}
        {answer && (
          <details>
            <summary>Submitted answer</summary>
            <pre className="payload-pre">{answer}</pre>
          </details>
        )}
      </div>
    </section>
  );
}
