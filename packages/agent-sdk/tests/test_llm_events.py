from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
from agentbench_sdk.schemas import RunResult
from agentbench_sdk.server import create_app
from fastapi import FastAPI

FAKE_LLM_KEY = "sk-" + "secret-test-key-that-must-not-leak"


class _Receiver:
    def __init__(self) -> None:
        self.steps: dict[int, dict[str, Any]] = {}
        self.complete_event = asyncio.Event()

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/steps"):
            for event in json.loads(request.content):
                self.steps.setdefault(event["seq"], event)
            return httpx.Response(204)
        if request.url.path.endswith("/complete"):
            self.complete_event.set()
            return httpx.Response(204)
        return httpx.Response(404)


def _request() -> dict[str, Any]:
    return {
        "run_id": "llm-test",
        "task": {
            "id": "task-one",
            "category": "coding",
            "prompt": "Implement a change.",
            "files": [{"path": "src/main.py", "content": "pass\n"}],
            "limits": {"timeout_s": 5, "max_steps": 20, "max_cost_usd": 1.0},
        },
        "llm": {
            "base_url": "https://llm.example/v1",
            "api_key": FAKE_LLM_KEY,
            "model": "test-model",
        },
        "callback": {"base_url": "https://callback.example", "token": "c" * 32},
    }


def _signed(value: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(value, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"shared-secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return body, {"X-AB-Timestamp": timestamp, "X-AB-Signature": signature}


async def _run(
    app: FastAPI, receiver: _Receiver, value: dict[str, Any]
) -> httpx.Response:
    body, headers = _signed(value)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://agent.test"
    ) as client:
        response = await client.post("/runs", content=body, headers=headers)
    await asyncio.wait_for(receiver.complete_event.wait(), timeout=8)
    return response


async def test_llm_hooks_record_usage_without_api_key() -> None:
    receiver = _Receiver()

    async def llm_reply(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer " + FAKE_LLM_KEY)
        return httpx.Response(
            200,
            json={
                "id": "completion-1",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            },
        )

    async def handler(ctx: Any) -> RunResult:
        await ctx.step("tool", {"message": ctx.llm.api_key, "callback": "c" * 32})
        result = await ctx.openai_client().chat.completions.create(
            model=ctx.llm.model,
            messages=[{"role": "user", "content": "hi"}],
        )
        return RunResult(answer=result.choices[0].message.content or "")

    app = create_app(handler, "shared-secret")
    app.state.callback_transport = httpx.MockTransport(receiver)
    app.state.llm_transport = httpx.MockTransport(llm_reply)
    response = await _run(app, receiver, _request())
    assert response.status_code == 202
    assert len(receiver.steps) == 2
    assert FAKE_LLM_KEY not in str(receiver.steps)
    assert "c" * 32 not in str(receiver.steps)
    event = next(step for step in receiver.steps.values() if step["type"] == "llm")
    assert event["payload"]["model"] == "test-model"
    assert event["payload"]["status_code"] == 200
    assert event["payload"]["usage"]["total_tokens"] == 5
    assert event["duration_ms"] >= 0


async def test_llm_retry_after_server_error_is_marked_retry() -> None:
    receiver = _Receiver()
    attempts = 0

    async def llm_reply(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"error": {"message": "try again"}})
        return httpx.Response(
            200,
            json={
                "id": "completion-2",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    async def handler(ctx: Any) -> RunResult:
        response = await ctx.openai_client().chat.completions.create(
            model=ctx.llm.model,
            messages=[{"role": "user", "content": "retry"}],
        )
        return RunResult(answer=response.choices[0].message.content or "")

    app = create_app(handler, "shared-secret")
    app.state.callback_transport = httpx.MockTransport(receiver)
    app.state.llm_transport = httpx.MockTransport(llm_reply)
    response = await _run(app, receiver, _request())
    assert response.status_code == 202
    assert attempts == 2
    assert [event["type"] for event in receiver.steps.values()] == ["llm", "retry"]
