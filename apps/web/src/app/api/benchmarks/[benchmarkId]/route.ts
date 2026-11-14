import { NextRequest } from "next/server";
import { apiClient } from "@/lib/api-server";
import { unavailable } from "@/lib/bff-response";
import type { Benchmark, BenchmarkRun } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ benchmarkId: string }> },
) {
  try {
    const { benchmarkId } = await params;
    const client = apiClient();
    const benchmarkResult = await client.GET("/benchmarks/{benchmark_id}", {
      params: { path: { benchmark_id: benchmarkId } },
    });
    if (!benchmarkResult.response.ok || !benchmarkResult.data) {
      return Response.json({ detail: "Benchmark not found." }, { status: benchmarkResult.response.status });
    }
    const cursor = request.nextUrl.searchParams.get("cursor") ?? undefined;
    const runsResult = await client.GET("/benchmarks/{benchmark_id}/runs", {
      params: {
        path: { benchmark_id: benchmarkId },
        query: { limit: 100, ...(cursor ? { cursor } : {}) },
      },
    });
    if (!runsResult.response.ok || !runsResult.data) {
      return Response.json({ detail: "Benchmark runs are unavailable." }, { status: runsResult.response.status });
    }
    return Response.json({
      benchmark: benchmarkResult.data as Benchmark,
      runs: runsResult.data as { items: BenchmarkRun[]; next_cursor: string | null },
    });
  } catch {
    return unavailable();
  }
}