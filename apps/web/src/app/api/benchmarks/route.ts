import { NextRequest } from "next/server";
import { apiClient } from "@/lib/api-server";
import { proxyResult, unavailable } from "@/lib/bff-response";
import { benchmarkRequestSchema } from "@/lib/validation";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const parsed = benchmarkRequestSchema.safeParse(await request.json());
    if (!parsed.success) {
      return Response.json({ detail: "Benchmark settings are invalid." }, { status: 422 });
    }
    return proxyResult(await apiClient().POST("/benchmarks", { body: parsed.data }));
  } catch {
    return unavailable();
  }
}