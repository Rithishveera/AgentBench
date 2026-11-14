import { NextRequest } from "next/server";
import { apiClient } from "@/lib/api-server";
import { proxyResult, unavailable } from "@/lib/bff-response";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> },
) {
  try {
    const { runId } = await params;
    const after = Number(request.nextUrl.searchParams.get("after_seq"));
    const requestedLimit = Number(request.nextUrl.searchParams.get("limit")) || 100;
    const afterSeq = Number.isInteger(after) && after >= -1 ? after : -1;
    const limit = Math.max(1, Math.min(100, Math.trunc(requestedLimit)));
    return proxyResult(
      await apiClient().GET("/runs/{run_id}/faults", {
        params: {
          path: { run_id: runId },
          query: { after_seq: afterSeq, limit },
        },
      }),
    );
  } catch {
    return unavailable();
  }
}