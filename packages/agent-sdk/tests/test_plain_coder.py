from __future__ import annotations

import asyncio
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from agentbench_sdk.client import AgentClient
from agentbench_sdk.schemas import RunRequest
from agentbench_sdk.server import create_app
from agentbench_tasks.loader import load_suite, visible_files
from agentbench_tasks.validators.tests_pass import _validate_patch

ROOT = Path(__file__).resolve().parents[3]
TASK_DIR = ROOT / "suites" / "coding" / "tasks" / "fix-failing-test"


def test_plain_coder_mock_patch_is_allowed_and_matches_reference(
    monkeypatch,
) -> None:
    namespace = runpy.run_path(str(ROOT / "agents" / "plain-coder" / "agent.py"))
    monkeypatch.setenv("MOCK", "1")
    task = SimpleNamespace(id="fix-failing-test")
    result = asyncio.run(namespace["handler"](SimpleNamespace(task=task, llm=None)))
    reference = (TASK_DIR / "reference" / "solution.patch").read_text(encoding="utf-8")
    assert result.patch.rstrip("\n") == reference.rstrip("\n")
    assert _validate_patch(result.patch.encode(), ["src/**"]) is None


async def test_mock_agent_accepts_signed_run_and_returns_reference_patch(
    monkeypatch,
) -> None:
    namespace = runpy.run_path(str(ROOT / "agents" / "plain-coder" / "agent.py"))
    monkeypatch.setenv("MOCK", "1")
    task = next(
        task
        for task in load_suite(ROOT / "suites" / "coding").tasks
        if task.id == "fix-failing-test"
    )
    reference = (TASK_DIR / "reference" / "solution.patch").read_text(encoding="utf-8")
    completed: dict[str, Any] = {}
    completion_event = asyncio.Event()

    async def callback(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/complete"):
            completed.update(__import__("json").loads(request.content))
            completion_event.set()
        return httpx.Response(204)

    app = create_app(namespace["handler"], "demo-secret")
    app.state.callback_transport = httpx.MockTransport(callback)
    request = RunRequest.model_validate(
        {
            "run_id": "plain-coder-demo",
            "task": {
                "id": task.id,
                "category": task.category,
                "prompt": task.prompt,
                "files": visible_files(task),
                "limits": task.limits.model_dump(),
            },
            "callback": {
                "base_url": "https://platform.example/callback",
                "token": "d" * 32,
            },
        }
    )
    client = AgentClient(transport=httpx.ASGITransport(app=app))
    await client.start_run("https://agent.example", "demo-secret", request)
    await asyncio.wait_for(completion_event.wait(), timeout=3)
    await client.close()

    patch = completed["patch"]
    assert patch.rstrip("\n") == reference.rstrip("\n")
    assert (
        _validate_patch(patch.encode(), task.validator.config["editable_globs"]) is None
    )
