"""Platform-side client for starting signed external-agent runs."""

from __future__ import annotations

import hashlib
import hmac
import time

import httpx

from agentbench_sdk.schemas import MAX_REQUEST_BYTES, RunRequest


class AgentClientError(Exception):
    """Raised when an external agent does not accept a run."""


class AgentClient:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        )

    async def start_run(
        self,
        agent_url: str,
        secret: str | bytes,
        run_request: RunRequest,
    ) -> None:
        body = run_request.model_dump_json(exclude_none=True).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError("run request exceeds 2 MB")
        timestamp = str(int(time.time()))
        key = secret.encode() if isinstance(secret, str) else secret
        signature = hmac.new(
            key,
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        response = await self._client.post(
            agent_url.rstrip("/") + "/runs",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-AB-Timestamp": timestamp,
                "X-AB-Signature": signature,
            },
        )
        if response.status_code != 202:
            raise AgentClientError(
                f"agent rejected run with HTTP {response.status_code}"
            )

    async def close(self) -> None:
        await self._client.aclose()
