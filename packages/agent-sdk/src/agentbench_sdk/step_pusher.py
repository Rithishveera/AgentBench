"""Buffered callback delivery that cannot block handler work."""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import httpx

from agentbench_sdk.schemas import CallbackConfig, StepEvent, StepType

_SECRET_VALUE = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
_SENSITIVE_KEY = re.compile(r"password|secret|token|api[_-]?key|authorization", re.I)
_TOKEN_COUNTS = {
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "input_tokens",
    "output_tokens",
}
_BATCH_SIZE = 20
_MAX_BUFFER = 200
_DRAIN_SECONDS = 8.0


def _redact(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if _SENSITIVE_KEY.search(str(key))
            and not (str(key) in _TOKEN_COUNTS and type(nested) is int)
            else _redact(nested, secrets)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        redacted = _SECRET_VALUE.sub("[REDACTED]", value)
        for secret in secrets:
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redacted
    return value


class StepLimitExceeded(Exception):
    """Raised when a handler exceeds its negotiated step limit."""


class StepPusher:
    def __init__(
        self,
        callback: CallbackConfig,
        max_steps: int,
        transport: httpx.AsyncBaseTransport | None = None,
        redacted_secrets: Iterable[str] = (),
    ) -> None:
        self._url = str(callback.base_url).rstrip("/") + "/steps"
        self._token = callback.token
        self._max_steps = max_steps
        self._redacted_secrets = tuple(redacted_secrets)
        self._buffer: deque[StepEvent] = deque()
        self._seq = 0
        self.steps_dropped = 0
        self._wake = asyncio.Event()
        self._closing = False
        self._close_deadline = 0.0
        self._last_flush = time.monotonic()
        self._last_heartbeat = self._last_flush
        self._client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=1.0, read=2.0, write=2.0, pool=1.0),
        )
        self._task = asyncio.create_task(self._run())

    async def push(
        self,
        event_type: StepType,
        payload: dict[str, Any],
        *,
        ok: bool,
        started_at: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        if self._seq >= self._max_steps:
            raise StepLimitExceeded("run exceeded max_steps")
        event = StepEvent(
            seq=self._seq,
            type=event_type,
            started_at=started_at or datetime.now(UTC).isoformat(),
            duration_ms=max(duration_ms, 0),
            ok=ok,
            payload=_redact(payload, self._redacted_secrets),
        )
        self._seq += 1
        if len(self._buffer) >= _MAX_BUFFER:
            self._buffer.popleft()
            self.steps_dropped += 1
        self._buffer.append(event)
        self._wake.set()

    async def close(self) -> int:
        self._closing = True
        self._close_deadline = time.monotonic() + _DRAIN_SECONDS
        self._wake.set()
        try:
            await self._task
        except Exception:
            self.steps_dropped += len(self._buffer)
            self._buffer.clear()
        finally:
            await self._client.aclose()
        return self.steps_dropped

    async def _post(self, events: list[StepEvent]) -> bool:
        try:
            response = await self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._token}"},
                json=[event.model_dump(mode="json") for event in events],
            )
            response.raise_for_status()
            return True
        except (httpx.HTTPError, ValueError):
            return False

    async def _run(self) -> None:
        backoff = 0.1
        while True:
            now = time.monotonic()
            flush_due = (
                len(self._buffer) >= _BATCH_SIZE or now - self._last_flush >= 0.5
            )
            heartbeat_due = now - self._last_heartbeat >= 10.0
            if self._closing and not self._buffer:
                return
            if self._closing and now >= self._close_deadline:
                self.steps_dropped += len(self._buffer)
                self._buffer.clear()
                return
            if self._buffer and (flush_due or self._closing):
                batch = list(self._buffer)[:_BATCH_SIZE]
                if await self._post(batch):
                    batch_sequences = {event.seq for event in batch}
                    while self._buffer and self._buffer[0].seq in batch_sequences:
                        self._buffer.popleft()
                    backoff = 0.1
                    self._last_flush = time.monotonic()
                    continue
                await asyncio.sleep(backoff + random.uniform(0, backoff / 4))
                backoff = min(backoff * 2, 1.0)
                continue
            if not self._buffer and heartbeat_due:
                if await self._post([]):
                    self._last_heartbeat = time.monotonic()
                else:
                    await asyncio.sleep(backoff + random.uniform(0, backoff / 4))
                    backoff = min(backoff * 2, 1.0)
                continue
            self._wake.clear()
            wait = (
                0.5 if self._buffer else max(0.1, 10.0 - (now - self._last_heartbeat))
            )
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=wait)
            except TimeoutError:
                pass
