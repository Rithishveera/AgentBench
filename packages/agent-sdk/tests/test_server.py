from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import pytest
from agentbench_sdk.schemas import RunResult
from agentbench_sdk.server import create_app
from fastapi import FastAPI

SECRET = "shared-test-secret"
FAKE_LLM_KEY = "sk-" + "secret-test-key-that-must-not-leak"


class _Receiver:
    def __init__(self) -> None:
        self.steps: dict[int, dict[str, Any]] = {}
        self.batches: list[int] = []
        self.completions: list[dict[str, Any]] = []
        self.complete_event = asyncio.Event()
        self.fail_once_after_store = False
        self.down_until = 0.0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/steps"):
            events = json.loads(request.content)
            self.batches.append(len(events))
            if time.monotonic() < self.down_until:
                return httpx.Response(503)
            for event in events:
                self.steps.setdefault(event["seq"], event)
            if self.fail_once_after_store:
                self.fail_once_after_store = False
                return httpx.Response(503)
            return httpx.Response(204)
        if request.url.path.endswith("/complete"):
            self.completions.append(json.loads(request.content))
            self.complete_event.set()
            return httpx.Response(204)
        return httpx.Response(404)


def _request_dict(
    run_id: str = "run-1",
    *,
    timeout_s: int = 2,
    max_steps: int = 100,
    llm: bool = False,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "task": {
            "id": "task-one",
            "category": "coding",
            "prompt": "Implement a change.",
            "files": [{"path": "src/main.py", "content": "pass\n"}],
            "limits": {
                "timeout_s": timeout_s,
                "max_steps": max_steps,
                "max_cost_usd": 1.0,
            },
        },
        "llm": (
            {
                "base_url": "https://llm.example/v1",
                "api_key": FAKE_LLM_KEY,
                "model": "test-model",
            }
            if llm
            else None
        ),
        "callback": {"base_url": "https://callback.example", "token": "c" * 32},
    }


def _signed_body(
    value: dict[str, Any], *, timestamp: str | None = None, secret: str = SECRET
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(value, separators=(",", ":")).encode()
    stamp = timestamp or str(int(time.time()))
    signature = hmac.new(
        secret.encode(), stamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return body, {"X-AB-Timestamp": stamp, "X-AB-Signature": signature}


def _app(handler: Any, receiver: _Receiver, *, max_concurrency: int = 4) -> FastAPI:
    app = create_app(handler, SECRET, max_concurrency=max_concurrency)
    app.state.callback_transport = httpx.MockTransport(receiver)
    return app


async def _post(
    app: FastAPI, value: dict[str, Any], headers: dict[str, str]
) -> httpx.Response:
    body = json.dumps(value, separators=(",", ":")).encode()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://agent.test"
    ) as client:
        return await client.post("/runs", content=body, headers=headers)


async def _wait_complete(receiver: _Receiver, timeout: float = 12) -> None:
    await asyncio.wait_for(receiver.complete_event.wait(), timeout=timeout)


async def test_bad_signature_stale_timestamp_and_replay_are_rejected() -> None:
    receiver = _Receiver()
    calls = 0

    async def handler(ctx: Any) -> RunResult:
        nonlocal calls
        calls += 1
        return RunResult(answer="ok")

    app = _app(handler, receiver)
    value = _request_dict()
    body, headers = _signed_body(value)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://agent.test"
    ) as client:
        bad = await client.post(
            "/runs", content=body, headers={**headers, "X-AB-Signature": "0" * 64}
        )
        stale_stamp = str(int(time.time()) - 301)
        _, stale_headers = _signed_body(value, timestamp=stale_stamp)
        stale = await client.post("/runs", content=body, headers=stale_headers)
        accepted = await client.post("/runs", content=body, headers=headers)
    assert bad.status_code == 401
    assert stale.status_code == 401
    assert accepted.status_code == 202
    await _wait_complete(receiver)
    replay = await _post(app, value, headers)
    assert replay.status_code == 409
    assert calls == 1
    assert len(receiver.completions) == 1


async def test_concurrency_limit_returns_503() -> None:
    receiver = _Receiver()
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(ctx: Any) -> RunResult:
        started.set()
        await release.wait()
        return RunResult(answer="ok")

    app = _app(handler, receiver, max_concurrency=1)
    first_value = _request_dict("first")
    first_body, first_headers = _signed_body(first_value)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://agent.test"
    ) as client:
        first = await client.post("/runs", content=first_body, headers=first_headers)
        await started.wait()
        second_value = _request_dict("second")
        second_body, second_headers = _signed_body(second_value)
        second = await client.post("/runs", content=second_body, headers=second_headers)
        release.set()
    await _wait_complete(receiver)
    assert first.status_code == 202
    assert second.status_code == 503
    assert len(receiver.completions) == 1


async def test_steps_are_ordered_batched_and_idempotent_after_retry() -> None:
    receiver = _Receiver()
    receiver.fail_once_after_store = True

    async def handler(ctx: Any) -> RunResult:
        for index in range(25):
            await ctx.step("tool", {"index": index})
        return RunResult(answer="done")

    app = _app(handler, receiver)
    value = _request_dict(max_steps=30)
    body, headers = _signed_body(value)
    response = await _post(app, value, headers)
    await _wait_complete(receiver)
    assert response.status_code == 202
    assert list(receiver.steps) == list(range(25))
    assert receiver.batches[:3] == [20, 20, 5]
    assert [receiver.steps[index]["payload"]["index"] for index in range(25)] == list(
        range(25)
    )


async def test_step_overflow_drops_oldest_and_reports_count() -> None:
    receiver = _Receiver()

    async def handler(ctx: Any) -> RunResult:
        for index in range(250):
            await ctx.step("tool", {"index": index})
        return RunResult(answer="done")

    app = _app(handler, receiver)
    value = _request_dict(max_steps=300)
    body, headers = _signed_body(value)
    response = await _post(app, value, headers)
    await _wait_complete(receiver)
    assert response.status_code == 202
    assert list(receiver.steps) == list(range(50, 250))
    assert receiver.completions[0]["steps_dropped"] == 50


async def test_max_steps_stops_handler_and_posts_error_completion() -> None:
    receiver = _Receiver()
    continued = False

    async def handler(ctx: Any) -> RunResult:
        nonlocal continued
        await ctx.step("tool", {"index": 0})
        await ctx.step("tool", {"index": 1})
        continued = True
        return RunResult(answer="should not be returned")

    app = _app(handler, receiver)
    value = _request_dict(max_steps=1)
    body, headers = _signed_body(value)
    response = await _post(app, value, headers)
    await _wait_complete(receiver)
    assert response.status_code == 202
    assert continued is False
    assert len(receiver.steps) == 1
    assert receiver.completions[0]["status"] == "error"
    assert "StepLimitExceeded" in receiver.completions[0]["error"]


async def test_callback_recovers_after_five_seconds_without_blocking_handler() -> None:
    receiver = _Receiver()
    receiver.down_until = time.monotonic() + 5
    finished = asyncio.Event()

    async def handler(ctx: Any) -> RunResult:
        await ctx.step("tool", {"name": "quick"})
        finished.set()
        return RunResult(answer="done")

    app = _app(handler, receiver)
    value = _request_dict()
    body, headers = _signed_body(value)
    started = time.monotonic()
    response = await _post(app, value, headers)
    await asyncio.wait_for(finished.wait(), timeout=1)
    await _wait_complete(receiver)
    assert response.status_code == 202
    assert time.monotonic() - started >= 5
    assert list(receiver.steps) == [0]
    assert receiver.completions[0]["steps_dropped"] == 0


@pytest.mark.parametrize("mode", ["exception", "timeout"])
async def test_handler_failure_and_timeout_post_one_completion(mode: str) -> None:
    receiver = _Receiver()

    async def handler(ctx: Any) -> RunResult:
        if mode == "exception":
            raise RuntimeError("must not leak " + FAKE_LLM_KEY)
        await asyncio.sleep(5)
        return RunResult(answer="late")

    app = _app(handler, receiver)
    value = _request_dict(timeout_s=1)
    body, headers = _signed_body(value)
    response = await _post(app, value, headers)
    await _wait_complete(receiver)
    assert response.status_code == 202
    assert len(receiver.completions) == 1
    assert receiver.completions[0]["status"] == "error"
    assert FAKE_LLM_KEY not in str(receiver.completions[0])
    if mode == "timeout":
        assert receiver.completions[0]["error"] == "handler timed out"
