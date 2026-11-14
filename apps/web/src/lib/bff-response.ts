import { NextResponse } from "next/server";

type ApiResult = { data?: unknown; response: Response };

export function proxyResult(result: ApiResult) {
  if (!result.response.ok) {
    return NextResponse.json(
      { detail: "The AgentBench API could not complete this request." },
      { status: result.response.status },
    );
  }
  return NextResponse.json(result.data ?? null, { status: result.response.status });
}

export function unavailable() {
  return NextResponse.json(
    { detail: "The AgentBench API is unavailable." },
    { status: 502 },
  );
}