import { NextRequest } from "next/server";
import { apiClient } from "@/lib/api-server";
import { proxyResult, unavailable } from "@/lib/bff-response";
import { registerAgentSchema } from "@/lib/validation";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const cursor = request.nextUrl.searchParams.get("cursor") ?? undefined;
    const requestedLimit = Number(request.nextUrl.searchParams.get("limit")) || 50;
    const limit = Math.max(1, Math.min(100, Math.trunc(requestedLimit)));
    const result = await apiClient().GET("/agents", {
      params: { query: { limit, ...(cursor ? { cursor } : {}) } },
    });
    return proxyResult(result);
  } catch {
    return unavailable();
  }
}

export async function POST(request: NextRequest) {
  try {
    const parsed = registerAgentSchema.safeParse(await request.json());
    if (!parsed.success) {
      return Response.json({ detail: "Agent details are invalid." }, { status: 422 });
    }
    const result = await apiClient().POST("/agents", { body: parsed.data });
    return proxyResult(result);
  } catch {
    return unavailable();
  }
}