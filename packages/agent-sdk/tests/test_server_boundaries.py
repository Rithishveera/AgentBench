from __future__ import annotations

from typing import Any

import httpx
from agentbench_sdk.schemas import MAX_REQUEST_BYTES, RunResult
from agentbench_sdk.server import create_app


async def _handler(ctx: Any) -> RunResult:
    return RunResult(answer="unused")


async def test_health_endpoint_returns_ok() -> None:
    app = create_app(_handler, "secret")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://agent.test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_oversized_request_is_rejected_before_signature_parsing() -> None:
    app = create_app(_handler, "secret")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://agent.test"
    ) as client:
        response = await client.post("/runs", content=b"x" * (MAX_REQUEST_BYTES + 1))
    assert response.status_code == 413
