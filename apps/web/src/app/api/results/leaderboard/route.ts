import { NextRequest } from "next/server";
import { apiClient } from "@/lib/api-server";
import { proxyResult, unavailable } from "@/lib/bff-response";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const category = request.nextUrl.searchParams.get("category") ?? undefined;
    return proxyResult(
      await apiClient().GET("/results/leaderboard", {
        params: { query: category ? { category } : {} },
      }),
    );
  } catch {
    return unavailable();
  }
}