"use client";

/**
 * useRunStream — WebSocket live-update hook for a benchmark.
 *
 * Connects via a single-use ticket fetched from the BFF.
 * On two consecutive WS failures, falls back to 3-second HTTP polling
 * (the same refetchInterval used by BenchmarkMonitor before this module).
 *
 * On reconnect the server sends a full snapshot, so the caller always
 * receives a consistent state.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { BenchmarkRun } from "@/lib/api-server";

export type RunUpdate = {
  run_id: string;
  agent_id: string;
  task_id: string;
  status: string;
  passed?: boolean;
  cost_usd?: number;
};

export type StreamSnapshot = {
  benchmark: {
    id: string;
    status: string;
    summary: Record<string, unknown> | null;
    created_at: string | null;
    finished_at: string | null;
  };
  runs: BenchmarkRun[];
};

export type StreamMessage =
  | ({ type: "snapshot" } & StreamSnapshot)
  | ({ type: "run_update" } & RunUpdate)
  | { type: "benchmark_complete"; benchmark_status: string }
  | { type: "ping" };

type UseRunStreamOptions = {
  benchmarkId: string;
  onMessage: (msg: StreamMessage) => void;
  /** Called when WS fails twice — signals the caller to enable polling. */
  onFallback: () => void;
  /** Whether the benchmark is already in a terminal state (stops trying). */
  terminal: boolean;
};

const BASE_DELAY_MS = 500;
const MAX_DELAY_MS = 30_000;
const WS_FAILURE_THRESHOLD = 2;

export function useRunStream({
  benchmarkId,
  onMessage,
  onFallback,
  terminal,
}: UseRunStreamOptions): void {
  const wsRef = useRef<WebSocket | null>(null);
  const failureCount = useRef(0);
  const retryTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMessageRef = useRef(onMessage);
  const onFallbackRef = useRef(onFallback);
  onMessageRef.current = onMessage;
  onFallbackRef.current = onFallback;

  const connect = useCallback(() => {
    if (terminal) return;
    if (failureCount.current >= WS_FAILURE_THRESHOLD) {
      onFallbackRef.current();
      return;
    }

    async function getTicket(): Promise<string | null> {
      try {
        const resp = await fetch(
          `/api/benchmarks/${encodeURIComponent(benchmarkId)}/stream-ticket`,
          { method: "POST" },
        );
        if (!resp.ok) return null;
        const data = (await resp.json()) as { ticket?: string };
        return data.ticket ?? null;
      } catch {
        return null;
      }
    }

    void (async () => {
      const ticket = await getTicket();
      if (!ticket) {
        failureCount.current++;
        if (failureCount.current >= WS_FAILURE_THRESHOLD) {
          onFallbackRef.current();
          return;
        }
        scheduleRetry();
        return;
      }

      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const url = `${proto}://${window.location.host}/api/benchmarks/${encodeURIComponent(benchmarkId)}/ws?ticket=${encodeURIComponent(ticket)}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as StreamMessage;
          onMessageRef.current(msg);
        } catch {
          // ignore malformed frames
        }
      };

      ws.onopen = () => {
        failureCount.current = 0;
      };

      ws.onclose = (event) => {
        wsRef.current = null;
        // 1000 = clean close (benchmark completed), 4404 = not found — don't retry
        if (event.code === 1000 || event.code === 4404 || terminal) return;
        failureCount.current++;
        if (failureCount.current >= WS_FAILURE_THRESHOLD) {
          onFallbackRef.current();
          return;
        }
        scheduleRetry();
      };

      ws.onerror = () => {
        // onerror is always followed by onclose
      };
    })();
  }, [benchmarkId, terminal]);

  function scheduleRetry() {
    const attempt = failureCount.current;
    const delay = Math.min(BASE_DELAY_MS * 2 ** attempt + Math.random() * 200, MAX_DELAY_MS);
    retryTimeout.current = setTimeout(() => {
      connect();
    }, delay);
  }

  useEffect(() => {
    if (terminal) return;
    connect();
    return () => {
      if (retryTimeout.current) clearTimeout(retryTimeout.current);
      wsRef.current?.close(1000);
      wsRef.current = null;
    };
    // connect is stable (useCallback with stable deps)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [benchmarkId, terminal]);
}
