"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { AlertTriangle, ArrowDownToLine, Filter, RotateCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RunStepCard } from "@/components/run-step-card";
import { TimeRuler } from "@/components/time-ruler";
import { formatUtcTime } from "@/lib/utils";
import type { CursorPage, FaultRecord, RunRecord, StepSummary } from "@/lib/api-server";

type TimelineEntry =
  | { kind: "step"; ts: string; step: StepSummary }
  | { kind: "fault"; ts: string; fault: FaultRecord };

async function getPage<T>(path: string, afterSeq: number): Promise<CursorPage<T>> {
  const response = await fetch(`${path}?after_seq=${afterSeq}&limit=100`);
  if (!response.ok) throw new Error("Timeline data is unavailable");
  return (await response.json()) as CursorPage<T>;
}

export function RunInspector({
  run,
  initialSteps,
  initialFaults,
}: Readonly<{
  run: RunRecord;
  initialSteps: CursorPage<StepSummary> | null;
  initialFaults: CursorPage<FaultRecord> | null;
}>) {
  const [typeFilter, setTypeFilter] = useState("all");
  const [resultFilter, setResultFilter] = useState("any");
  const [pendingJump, setPendingJump] = useState<number | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stepButtons = useRef(new Map<number, HTMLButtonElement>());
  const stepsQuery = useInfiniteQuery({
    queryKey: ["run-steps", run.id],
    queryFn: ({ pageParam }) => getPage<StepSummary>(`/api/runs/${run.id}/steps`, pageParam),
    initialPageParam: -1,
    initialData: initialSteps ? { pages: [initialSteps], pageParams: [-1] } : undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const faultsQuery = useInfiniteQuery({
    queryKey: ["run-faults", run.id],
    queryFn: ({ pageParam }) => getPage<FaultRecord>(`/api/runs/${run.id}/faults`, pageParam),
    initialPageParam: -1,
    initialData: initialFaults ? { pages: [initialFaults], pageParams: [-1] } : undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const allSteps = stepsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const allFaults = faultsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const visibleSteps = useMemo(
    () => allSteps.filter((step) =>
      (typeFilter === "all" || step.type === typeFilter)
      && (resultFilter === "any" || (resultFilter === "failed" ? !step.ok : step.ok)),
    ),
    [allSteps, resultFilter, typeFilter],
  );
  const entries = useMemo<TimelineEntry[]>(() => [
    ...visibleSteps.map((step): TimelineEntry => ({ kind: "step", ts: step.ts, step })),
    ...allFaults.map((fault): TimelineEntry => ({ kind: "fault", ts: fault.ts, fault })),
  ].sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts)), [allFaults, visibleSteps]);
  const faultCounts = useMemo(
    () => allFaults.reduce<Record<string, number>>((counts, fault) => {
      counts[fault.fault_type] = (counts[fault.fault_type] ?? 0) + 1;
      return counts;
    }, {}),
    [allFaults],
  );
  const virtualized = run.steps_count > 200;
  const useVirtualList = virtualized && hydrated;
  const morePages = Boolean(stepsQuery.hasNextPage || faultsQuery.hasNextPage);
  const virtualizer = useVirtualizer({
    count: virtualized ? entries.length + Number(morePages) : entries.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: (index) => entries[index]?.kind === "fault" ? 70 : 112,
    overscan: 10,
    getItemKey: (index) => {
      const entry = entries[index];
      return entry?.kind === "fault" ? `fault-${entry.fault.seq}` : entry?.step.seq ?? index;
    },
  });

  useEffect(() => {
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (pendingJump === null) return;
    const index = entries.findIndex((entry) => entry.kind === "step" && entry.step.seq === pendingJump);
    if (index < 0) return;
    if (useVirtualList) virtualizer.scrollToIndex(index, { align: "center" });
    else stepButtons.current.get(pendingJump)?.scrollIntoView({ block: "center" });
    requestAnimationFrame(() => stepButtons.current.get(pendingJump)?.focus());
    setPendingJump(null);
  }, [entries, pendingJump, useVirtualList, virtualizer]);

  async function loadAllStepsUntil(predicate: (step: StepSummary) => boolean) {
    let data = stepsQuery.data;
    let match = data?.pages.flatMap((page) => page.items).find(predicate);
    while (!match && stepsQuery.hasNextPage) {
      const next = await stepsQuery.fetchNextPage();
      data = next.data;
      match = data?.pages.flatMap((page) => page.items).find(predicate);
      if (!next.hasNextPage) break;
    }
    return match;
  }

  async function jumpToFirstError() {
    setTypeFilter("all");
    setResultFilter("any");
    const match = await loadAllStepsUntil((step) => !step.ok);
    if (match) setPendingJump(match.seq);
  }

  async function jumpToStep(seq: number) {
    setTypeFilter("all");
    setResultFilter("any");
    const match = await loadAllStepsUntil((step) => step.seq === seq);
    if (match) setPendingJump(match.seq);
  }

  function onTimelineScroll() {
    const element = scrollRef.current;
    if (!element || element.scrollHeight - element.scrollTop - element.clientHeight > 500) return;
    loadNextPage();
  }

  function loadNextPage() {
    if (stepsQuery.hasNextPage && !stepsQuery.isFetchingNextPage) void stepsQuery.fetchNextPage();
    else if (faultsQuery.hasNextPage && !faultsQuery.isFetchingNextPage) void faultsQuery.fetchNextPage();
  }

  function focusNeighbor(seq: number, direction: -1 | 1) {
    const index = visibleSteps.findIndex((step) => step.seq === seq);
    const next = visibleSteps[index + direction];
    if (!next) return;
    const entryIndex = entries.findIndex((entry) => entry.kind === "step" && entry.step.seq === next.seq);
    if (useVirtualList) virtualizer.scrollToIndex(entryIndex, { align: "auto" });
    requestAnimationFrame(() => stepButtons.current.get(next.seq)?.focus());
  }

  const isPending = !stepsQuery.data && stepsQuery.isPending;
  const hasFailedSteps = allSteps.some((step) => !step.ok);

  return (
    <>
      <section className="surface timeline-surface" aria-labelledby="timeline-title">
        <div className="surface-header timeline-header">
          <div><h2 className="section-title" id="timeline-title">Execution timeline</h2><p className="section-note">Expand an event to load its payload on demand.</p></div>
          <div className="toolbar-group">
            <Button variant="outline" size="small" onClick={() => void jumpToFirstError()} disabled={!hasFailedSteps && !stepsQuery.hasNextPage} aria-label="Jump to first error"><AlertTriangle size={14} />First error</Button>
          </div>
        </div>
        <div className="timeline-toolbar">
          <label className="filter-label"><Filter size={13} aria-hidden="true" />Type
            <select aria-label="Filter steps by type" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              {STEP_TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="filter-label">Outcome
            <select aria-label="Filter steps by outcome" value={resultFilter} onChange={(event) => setResultFilter(event.target.value)}>
              <option value="any">All outcomes</option><option value="failed">Failed</option><option value="ok">Successful</option>
            </select>
          </label>
          <span className="timeline-count">{visibleSteps.length.toLocaleString()} of {run.steps_count.toLocaleString()} steps loaded</span>
          <Button variant="quiet" size="small" onClick={() => { void stepsQuery.refetch(); void faultsQuery.refetch(); }} aria-label="Refresh timeline"><RotateCw size={14} /></Button>
        </div>
        <div className="surface-body timeline-body">
          <TimeRuler
            steps={allSteps}
            faults={allFaults}
            run={run}
            complete={!stepsQuery.hasNextPage}
            onJump={(seq) => void jumpToStep(seq)}
          />
          {isPending ? <div className="empty-state">Loading run timeline…</div> : stepsQuery.isError && !stepsQuery.data ? (
            <div className="empty-state" role="alert">Timeline data could not be loaded.</div>
          ) : entries.length === 0 ? (
            <div className="empty-state">No events match these filters.</div>
          ) : (
            <div className="timeline-scroll" ref={scrollRef} onScroll={onTimelineScroll} aria-label="Run events">
              {useVirtualList ? (
                <div className="timeline-virtual-space" style={{ height: virtualizer.getTotalSize() }}>
                  {virtualizer.getVirtualItems().map((item) => {
                    const entry = entries[item.index];
                    if (!entry) return <div key={item.key} className="timeline-loading-row" style={{ transform: `translateY(${item.start}px)` }}>Loading more events…</div>;
                    const nextStepSeq = entry.kind === "fault"
                      ? entries.slice(item.index + 1).find((candidate) => candidate.kind === "step")?.step.seq
                      : undefined;
                    return (
                      <div key={item.key} className="timeline-virtual-row" ref={virtualizer.measureElement} data-index={item.index} style={{ transform: `translateY(${item.start}px)` }}>
                        <TimelineEntryView entry={entry} runId={run.id} registerButton={registerButton} onArrow={focusNeighbor} onJump={jumpToStep} nextStepSeq={nextStepSeq} />
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="timeline-list">
                  {entries.map((entry, index) => {
                    const nextStepSeq = entry.kind === "fault"
                      ? entries.slice(index + 1).find((candidate) => candidate.kind === "step")?.step.seq
                      : undefined;
                    return <TimelineEntryView key={entry.kind === "fault" ? `fault-${entry.fault.seq}` : `step-${entry.step.seq}`} entry={entry} runId={run.id} registerButton={registerButton} onArrow={focusNeighbor} onJump={jumpToStep} nextStepSeq={nextStepSeq} />;
                  })}
                </div>
              )}
              {stepsQuery.isFetchingNextPage && <p className="timeline-fetching"><RotateCw size={13} />Loading more steps…</p>}
            </div>
          )}
          {!virtualized && morePages && <Button variant="outline" className="mt-3" onClick={loadNextPage}><ArrowDownToLine size={14} />Load next page</Button>}
        </div>
      </section>
    </>
  );

  function registerButton(seq: number, element: HTMLButtonElement | null) {
    if (element) stepButtons.current.set(seq, element);
    else stepButtons.current.delete(seq);
  }
}

function TimelineEntryView({
  entry,
  runId,
  registerButton,
  onArrow,
  onJump,
  nextStepSeq,
}: Readonly<{
  entry: TimelineEntry;
  runId: string;
  registerButton: (seq: number, element: HTMLButtonElement | null) => void;
  onArrow: (seq: number, direction: -1 | 1) => void;
  onJump: (seq: number) => void;
  nextStepSeq?: number;
}>) {
  if (entry.kind === "step") {
    return <RunStepCard runId={runId} step={entry.step} registerButton={registerButton} onArrow={onArrow} />;
  }
  const reaction = entry.fault.agent_reaction ?? "unclassified";
  return (
    <article className="fault-marker" aria-label={`${entry.fault.fault_type}, ${reaction}`}>
      <span className="fault-marker-icon"><AlertTriangle size={15} aria-hidden="true" /></span>
      <div className="fault-marker-main">
        <span><strong>{entry.fault.fault_type}</strong> injected</span>
        <time dateTime={entry.fault.ts}>{formatUtcTime(entry.fault.ts)}</time>
        <Badge tone={reaction === "retried_ok" ? "success" : reaction === "gave_up" ? "danger" : "warning"}>{reaction}</Badge>
      </div>
      <button className="fault-jump" disabled={nextStepSeq === undefined} onClick={() => nextStepSeq !== undefined && onJump(nextStepSeq)}>Jump to next step</button>
    </article>
  );
}

const STEP_TYPE_OPTIONS = [
  { value: "all", label: "All types" },
  { value: "llm", label: "LLM" },
  { value: "tool", label: "Tool" },
  { value: "retry", label: "Retry" },
] as const;
