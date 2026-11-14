import { apiClient } from "@/lib/api-server";
import { proxyResult, unavailable } from "@/lib/bff-response";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return proxyResult(await apiClient().GET("/suites"));
  } catch {
    return unavailable();
  }
}