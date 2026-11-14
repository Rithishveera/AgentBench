"""Per-run task context passed to agent handlers."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from openai import AsyncOpenAI

from agentbench_sdk.schemas import LLMConfig, RunTask, StepType
from agentbench_sdk.step_pusher import StepPusher


class RunContext:
    def __init__(
        self,
        task: RunTask,
        llm: LLMConfig | None,
        pusher: StepPusher,
        llm_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.task = task
        self.llm = llm
        self._pusher = pusher
        self._llm_transport = llm_transport
        self._openai_client: AsyncOpenAI | None = None

    async def step(
        self,
        event_type: StepType,
        payload: dict[str, Any],
        *,
        ok: bool = True,
        started_at: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        await self._pusher.push(
            event_type,
            payload,
            ok=ok,
            started_at=started_at,
            duration_ms=duration_ms,
        )

    @asynccontextmanager
    async def tool(self, name: str) -> AsyncIterator[None]:
        started = time.monotonic()
        started_at = datetime.now(UTC).isoformat()
        ok = False
        payload: dict[str, Any] = {"name": name}
        try:
            yield
            ok = True
        except Exception as error:
            payload["error_type"] = type(error).__name__
            raise
        finally:
            await self.step(
                "tool",
                payload,
                ok=ok,
                started_at=started_at,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

    def openai_client(self) -> AsyncOpenAI:
        if self.llm is None:
            raise RuntimeError("this run has no LLM configuration")
        if self._openai_client is None:
            http_client = httpx.AsyncClient(
                event_hooks={
                    "request": [self._llm_request],
                    "response": [self._llm_response],
                },
                transport=self._llm_transport,
                follow_redirects=False,
                timeout=httpx.Timeout(connect=5.0, read=60.0, write=30.0, pool=5.0),
            )
            self._openai_client = AsyncOpenAI(
                api_key=self.llm.api_key,
                base_url=str(self.llm.base_url),
                http_client=http_client,
                max_retries=2,
            )
        return self._openai_client

    async def close(self) -> None:
        if self._openai_client is not None:
            await self._openai_client.close()

    async def _llm_request(self, request: httpx.Request) -> None:
        request.extensions["agentbench_started"] = time.monotonic()
        request.extensions["agentbench_started_at"] = datetime.now(UTC).isoformat()

    async def _llm_response(self, response: httpx.Response) -> None:
        request = response.request
        started = request.extensions.get("agentbench_started", time.monotonic())
        started_at = request.extensions.get(
            "agentbench_started_at", datetime.now(UTC).isoformat()
        )
        try:
            await response.aread()
            response_data = json.loads(response.content)
        except (httpx.HTTPError, json.JSONDecodeError):
            response_data = {}
        try:
            request_data = json.loads(request.content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            request_data = {}
        usage = response_data.get("usage", {})
        error = response_data.get("error")
        error_text = (
            " ".join(
                str(error.get(field) or "") for field in ("message", "type", "code")
            )
            if isinstance(error, dict)
            else str(error or "")
        ).casefold()
        budget_exceeded = (
            response.status_code in {402, 429}
            and "budget" in error_text
            and "exceed" in error_text
        )
        retry_count = request.headers.get("x-stainless-retry-count", "0")
        try:
            is_retry = int(retry_count) > 0
        except ValueError:
            is_retry = False
        payload = {
            "model": response_data.get("model", request_data.get("model")),
            "status_code": response.status_code,
            "usage": {
                key: usage[key]
                for key in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "input_tokens",
                    "output_tokens",
                )
                if key in usage
            },
        }
        if budget_exceeded:
            payload["budget_exceeded"] = True
        await self.step(
            "retry" if is_retry else "llm",
            payload,
            ok=response.is_success,
            started_at=str(started_at),
            duration_ms=int((time.monotonic() - float(started)) * 1000),
        )
