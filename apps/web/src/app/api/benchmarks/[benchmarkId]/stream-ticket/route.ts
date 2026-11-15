/**
 * BFF: POST /api/benchmarks/[benchmarkId]/stream-ticket
 * Calls the Python API (server-side, with API_KEY) and returns the ticket.
 * The browser never sees the API key.
 */
import { apiClient } from "@/lib/api-server";
import { unavailable } from "@/lib/bff-response";
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ benchmarkId: string }> },
) {
  try {
    const { benchmarkId } = await params;
    const client = apiClient();
    const result = await client.POST(
      "/benchmarks/{benchmark_id}/stream-ticket" as never,
      { params: { path: { benchmark_id: benchmarkId } } } as never,
    );
    if (!(result as { response: Response }).response.ok) {
      return Response.json({ detail: "Could not issue stream ticket." }, { status: 502 });
    }
    return Response.json((result as { data: unknown }).data);
  } catch {
    return unavailable();
  }
}
