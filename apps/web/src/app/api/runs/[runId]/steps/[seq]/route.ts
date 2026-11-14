import { apiClient } from "@/lib/api-server";
import { proxyResult, unavailable } from "@/lib/bff-response";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ runId: string; seq: string }> },
) {
  try {
    const { runId, seq } = await params;
    const sequence = Number(seq);
    if (!Number.isSafeInteger(sequence) || sequence < 0) {
      return Response.json({ detail: "Step sequence is invalid." }, { status: 400 });
    }
    return proxyResult(
      await apiClient().GET("/runs/{run_id}/steps/{seq}", {
        params: { path: { run_id: runId, seq: sequence } },
      }),
    );
  } catch {
    return unavailable();
  }
}