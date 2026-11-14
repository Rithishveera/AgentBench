import { apiClient } from "@/lib/api-server";
import { proxyResult, unavailable } from "@/lib/bff-response";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ suiteId: string }> },
) {
  try {
    const { suiteId } = await params;
    return proxyResult(
      await apiClient().GET("/suites/{suite_id}/tasks", {
        params: { path: { suite_id: suiteId } },
      }),
    );
  } catch {
    return unavailable();
  }
}