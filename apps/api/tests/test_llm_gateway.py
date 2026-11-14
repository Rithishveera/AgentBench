from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import respx
from agentbench_api.config import Settings
from agentbench_api.services.llm_gateway import (
    get_run_usage,
    managed_run_key,
    mint_run_key,
    revoke_key,
)
from cryptography.fernet import Fernet
from httpx import Response


def _settings() -> Settings:
    return Settings(
        API_KEY="api-key",
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        DATABASE_URL="postgresql+asyncpg://agentbench:pw@localhost/agentbench",
        REDIS_URL="redis://:pw@localhost:6379/0",
        LITELLM_MASTER_KEY="sk-master-test",
        LITELLM_URL="http://litellm.test",
        _env_file=None,
    )


@pytest.mark.asyncio
@respx.mock
async def test_mint_run_key_scopes_budget_models_alias_and_ttl() -> None:
    run_id = uuid4()
    route = respx.post("http://litellm.test/key/generate").mock(
        return_value=Response(200, json={"key": "sk-run-key-test"})
    )

    key = await mint_run_key(
        run_id,
        ["agentbench-default"],
        max_budget_usd=1.25,
        ttl=timedelta(seconds=90),
        settings=_settings(),
    )

    request = route.calls.last.request
    payload = json.loads(request.content)
    assert key == "sk-run-key-test"
    assert request.headers["Authorization"] == "Bearer sk-master-test"
    assert "sk-master-test" not in request.content.decode("utf-8")
    assert payload == {
        "models": ["agentbench-default"],
        "max_budget": 1.25,
        "duration": "90s",
        "key_alias": str(run_id),
        "metadata": {"run_id": str(run_id)},
        "allowed_routes": ["llm_api_routes"],
    }


@pytest.mark.asyncio
@respx.mock
async def test_revoke_run_key_uses_management_key() -> None:
    route = respx.post("http://litellm.test/key/delete").mock(
        return_value=Response(200, json={"deleted_keys": ["sk-run-key-test"]})
    )

    await revoke_key("sk-run-key-test", settings=_settings())

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer sk-master-test"
    assert json.loads(request.content) == {"keys": ["sk-run-key-test"]}


@pytest.mark.asyncio
@respx.mock
async def test_managed_run_key_revokes_after_body_exception() -> None:
    respx.post("http://litellm.test/key/generate").mock(
        return_value=Response(200, json={"key": "sk-run-key-test"})
    )
    delete = respx.post("http://litellm.test/key/delete").mock(
        return_value=Response(200, json={"deleted_keys": ["sk-run-key-test"]})
    )

    with pytest.raises(RuntimeError, match="run failed"):
        async with managed_run_key(
            "run-id",
            ["agentbench-default"],
            max_budget_usd=1.0,
            ttl=30,
            settings=_settings(),
        ) as key:
            assert key == "sk-run-key-test"
            raise RuntimeError("run failed")

    assert delete.called


class FakeSession:
    def __init__(self, run: object) -> None:
        self.run = run

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, _model: object, _run_id: object) -> object:
        return self.run


class FakeSessionFactory:
    def __init__(self, run: object) -> None:
        self.run = run

    def __call__(self) -> FakeSession:
        return FakeSession(self.run)


@pytest.mark.asyncio
@respx.mock
async def test_get_run_usage_aggregates_spend_logs_by_key_hash(monkeypatch) -> None:
    run_id = uuid4()
    started_at = datetime(2026, 11, 14, 0, 0, 0, tzinfo=UTC)
    finished_at = datetime(2026, 11, 14, 0, 0, 10, tzinfo=UTC)
    run = SimpleNamespace(
        litellm_key_hash="f" * 64,
        started_at=started_at,
        finished_at=finished_at,
    )
    monkeypatch.setattr(
        "agentbench_api.services.llm_gateway.get_session_factory",
        lambda: FakeSessionFactory(run),
    )
    route = respx.get("http://litellm.test/spend/logs/v2").mock(
        side_effect=[
            Response(
                200,
                json={
                    "data": [
                        {"prompt_tokens": 12, "completion_tokens": 5, "spend": 0.02}
                    ],
                    "total_pages": 2,
                },
            ),
            Response(
                200,
                json={
                    "data": [{"input_tokens": 3, "output_tokens": 2, "spend": 0.03}],
                    "total_pages": 2,
                },
            ),
        ]
    )

    usage = await get_run_usage(run_id, settings=_settings())

    assert usage == {
        "tokens_in": 15,
        "tokens_out": 7,
        "cost_usd": pytest.approx(0.05),
        "calls": 2,
    }
    assert len(route.calls) == 2
    assert route.calls[0].request.url.params["api_key"] == "f" * 64
    assert route.calls[0].request.url.params["start_date"] == "2026-11-13 23:59:59"
    assert route.calls[0].request.url.params["end_date"] == "2026-11-14 00:00:11"
    assert route.calls[1].request.url.params["page"] == "2"


@pytest.mark.asyncio
async def test_live_litellm_virtual_key_usage() -> None:
    required = (
        "LITELLM_LIVE_TEST",
        "LITELLM_MASTER_KEY",
        "LITELLM_URL",
        "LITELLM_MODEL",
        "OPENAI_API_KEY",
    )
    if (
        any(not os.environ.get(name) for name in required)
        or os.environ["LITELLM_LIVE_TEST"] != "1"
    ):
        pytest.skip("Set LiteLLM live-test variables to enable this integration test")

    settings = Settings(
        API_KEY="api-key",
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        DATABASE_URL="postgresql+asyncpg://agentbench:pw@localhost/agentbench",
        REDIS_URL="redis://:pw@localhost:6379/0",
        LITELLM_MASTER_KEY=os.environ["LITELLM_MASTER_KEY"],
        LITELLM_URL=os.environ["LITELLM_URL"],
        LITELLM_MODEL=os.environ["LITELLM_MODEL"],
        _env_file=None,
    )
    run_id = uuid4()
    started_at = datetime.now(UTC) - timedelta(minutes=1)
    key: str | None = None
    try:
        key = await mint_run_key(
            run_id,
            [settings.litellm_model],
            max_budget_usd=1.0,
            ttl=timedelta(minutes=5),
            settings=settings,
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                settings.litellm_url.rstrip("/") + "/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.litellm_model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 8,
                },
            )
            response.raise_for_status()
        run = SimpleNamespace(
            litellm_key_hash=hashlib.sha256(key.encode("utf-8")).hexdigest(),
            started_at=started_at,
            finished_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        usage = await get_run_usage(
            run_id,
            settings=settings,
            session_factory=FakeSessionFactory(run),
        )
        assert usage["calls"] >= 1
        assert usage["tokens_in"] > 0
    finally:
        if key is not None:
            await revoke_key(key, settings=settings)
