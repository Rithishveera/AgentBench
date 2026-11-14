from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
import respx
from agentbench_api.config import Settings
from agentbench_api.services import runner
from agentbench_sdk.schemas import CallbackConfig, RunLimits, RunRequest, RunTask
from cryptography.fernet import Fernet
from httpx import Response
from pydantic import AnyHttpUrl


class _FakeSession:
    def __init__(self, run: SimpleNamespace, agent: SimpleNamespace) -> None:
        self.run = run
        self.agent = agent

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, model: object, _key: object) -> object:
        if model is runner.Run:
            return self.run
        if model is runner.Agent:
            return self.agent
        return object()

    async def commit(self) -> None:
        return None

    async def refresh(self, _run: object) -> None:
        return None


class _FakeSessionFactory:
    def __init__(self, run: SimpleNamespace, agent: SimpleNamespace) -> None:
        self.run = run
        self.agent = agent

    def __call__(self) -> _FakeSession:
        return _FakeSession(self.run, self.agent)


class _Verdict:
    def model_dump(self, *, mode: str) -> dict[str, bool]:
        assert mode == "json"
        return {"passed": True}


def _settings() -> Settings:
    return Settings(
        API_KEY="api-key",
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        DATABASE_URL="postgresql+asyncpg://agentbench:pw@localhost/agentbench",
        REDIS_URL="redis://:pw@localhost:6379/0",
        LITELLM_MASTER_KEY="sk-master-test",
        LITELLM_URL="http://litellm.test",
        LITELLM_MODEL="agentbench-default",
        AGENT_CALLBACK_BASE_URL="http://agent-ingress.test/internal",
        _env_file=None,
    )


def _request(run_id: str) -> RunRequest:
    return RunRequest(
        run_id=run_id,
        task=RunTask(
            id="task-one",
            category="coding",
            prompt="Implement the task.",
            files=[],
            limits=RunLimits(timeout_s=1, max_steps=10, max_cost_usd=1.25),
        ),
        callback=CallbackConfig(
            base_url=AnyHttpUrl("http://agent-ingress.test/internal"),
            token="placeholder-token-value",
        ),
    )


def _patch_runner(monkeypatch, run, agent, request, captured, fail_start=False) -> None:
    task = SimpleNamespace(limits=SimpleNamespace(timeout_s=1, max_cost_usd=1.25))

    async def claim(_session, _run_id):
        run.status = "running"
        return run

    async def task_model(_task_record):
        return task

    async def request_for(*_args, **_kwargs):
        return task, request

    async def terminal(_session, _run_id, status, **values):
        run.status = status
        run.failure_cause = values.get("failure_cause")
        run.verdict = values.get("verdict")
        run.artifact = values.get("artifact")
        return True

    class FakeAgentClient:
        async def start_run(self, _url, _secret, run_request) -> None:
            captured.append(run_request)
            if fail_start:
                raise RuntimeError("agent unavailable")
            run.artifact = {"patch": "diff"}

        async def close(self) -> None:
            return None

    async def no_wait(_seconds: int) -> None:
        return None

    async def record_usage(*_args, **_kwargs):
        return {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0}

    async def validate(*_args):
        return _Verdict()

    monkeypatch.setattr(runner, "claim_run", claim)
    monkeypatch.setattr(runner, "_task_model", task_model)
    monkeypatch.setattr(runner, "_run_request_for", request_for)
    monkeypatch.setattr(runner, "mark_run_terminal", terminal)
    monkeypatch.setattr(runner, "AgentClient", FakeAgentClient)
    monkeypatch.setattr(runner, "asyncio_sleep", no_wait)
    monkeypatch.setattr(runner, "record_run_usage", record_usage)
    monkeypatch.setattr(runner, "decrypt_agent_secret", lambda *_args: "agent-secret")
    monkeypatch.setattr(runner, "validate_run", validate)
    monkeypatch.setattr(runner, "DockerSandbox", lambda: object())


@pytest.mark.asyncio
@respx.mock
async def test_runner_sends_only_virtual_key_and_reconciles_usage(monkeypatch) -> None:
    run_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        status="queued",
        agent_id=uuid4(),
        task_id="task-one",
        duration_ms=1,
        artifact=None,
        litellm_key_hash=None,
    )
    agent = SimpleNamespace(
        id=run.agent_id,
        url="http://agent.test",
        secret_encrypted="encrypted",
    )
    request = _request(str(run_id))
    captured: list[RunRequest] = []
    factory = _FakeSessionFactory(run, agent)
    settings = _settings()
    _patch_runner(monkeypatch, run, agent, request, captured)
    respx.post("http://litellm.test/key/generate").mock(
        return_value=Response(200, json={"key": "sk-run-key-test"})
    )
    delete = respx.post("http://litellm.test/key/delete").mock(
        return_value=Response(200, json={"deleted_keys": ["sk-run-key-test"]})
    )

    result = await runner.execute_run(
        run_id,
        session_factory=factory,
        settings=settings,
    )

    assert result is True
    assert run.status == "completed"
    assert run.litellm_key_hash is not None
    assert len(captured) == 1
    assert captured[0].llm is not None
    assert captured[0].llm.api_key == "sk-run-key-test"
    assert "sk-master-test" not in captured[0].model_dump_json()
    assert "test-provider-key" not in captured[0].model_dump_json()
    assert delete.called


@pytest.mark.asyncio
@respx.mock
async def test_runner_revokes_key_when_agent_start_raises(monkeypatch) -> None:
    run_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        status="queued",
        agent_id=uuid4(),
        task_id="task-one",
        duration_ms=1,
        artifact=None,
        litellm_key_hash=None,
    )
    agent = SimpleNamespace(
        id=run.agent_id,
        url="http://agent.test",
        secret_encrypted="encrypted",
    )
    captured: list[RunRequest] = []
    factory = _FakeSessionFactory(run, agent)
    settings = _settings()
    _patch_runner(
        monkeypatch,
        run,
        agent,
        _request(str(run_id)),
        captured,
        fail_start=True,
    )
    respx.post("http://litellm.test/key/generate").mock(
        return_value=Response(200, json={"key": "sk-run-key-test"})
    )
    delete = respx.post("http://litellm.test/key/delete").mock(
        return_value=Response(200, json={"deleted_keys": ["sk-run-key-test"]})
    )

    result = await runner.execute_run(
        run_id,
        session_factory=factory,
        settings=settings,
    )

    assert result is False
    assert run.failure_cause == "start_run"
    assert delete.called
