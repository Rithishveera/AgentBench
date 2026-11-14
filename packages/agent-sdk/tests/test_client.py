from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest
from agentbench_sdk.client import AgentClient, AgentClientError
from agentbench_sdk.integrations.plain import serve
from agentbench_sdk.schemas import RunRequest, RunResult


def _request() -> RunRequest:
    return RunRequest.model_validate(
        {
            "run_id": "client-test",
            "task": {
                "id": "task-one",
                "category": "coding",
                "prompt": "Implement a change.",
                "files": [{"path": "src/main.py", "content": "pass\n"}],
                "limits": {
                    "timeout_s": 30,
                    "max_steps": 20,
                    "max_cost_usd": 1.0,
                },
            },
            "callback": {
                "base_url": "https://callback.example",
                "token": "c" * 32,
            },
        }
    )


async def test_client_signs_exact_body_and_posts_runs() -> None:
    requests: list[httpx.Request] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202)

    client = AgentClient(transport=httpx.MockTransport(transport))
    await client.start_run("https://agent.example", "secret", _request())
    await client.close()

    request = requests[0]
    body = request.content
    timestamp = request.headers["X-AB-Timestamp"]
    expected = hmac.new(
        b"secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert request.url.path == "/runs"
    assert request.headers["X-AB-Signature"] == expected
    assert json.loads(body)["run_id"] == "client-test"


async def test_client_does_not_follow_redirects() -> None:
    calls: list[str] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://elsewhere.test/runs"})

    client = AgentClient(transport=httpx.MockTransport(transport))
    with pytest.raises(AgentClientError, match="307"):
        await client.start_run("https://agent.example", "secret", _request())
    await client.close()
    assert len(calls) == 1


def test_plain_serve_uses_secret_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(app: Any, *, host: str, port: int) -> None:
        captured.update(app=app, host=host, port=port)

    monkeypatch.setenv("AGENT_SECRET", "test-secret")
    monkeypatch.setattr("agentbench_sdk.integrations.plain.uvicorn.run", fake_run)

    async def handler(ctx: Any) -> RunResult:
        return RunResult(answer="ok")

    serve(handler)
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8000
    assert captured["app"] is not None


def test_plain_serve_requires_agent_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_SECRET", raising=False)

    async def handler(ctx: Any) -> RunResult:
        return RunResult(answer="ok")

    with pytest.raises(RuntimeError, match="AGENT_SECRET"):
        serve(handler)
