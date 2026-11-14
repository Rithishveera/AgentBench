from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from agentbench_api import deps
from agentbench_api.config import Settings
from agentbench_api.crypto import decrypt_agent_secret, encrypt_agent_secret
from agentbench_api.db import create_engine, get_engine, get_session_factory
from agentbench_api.repositories import bulk_insert_steps
from agentbench_sdk.schemas import StepEvent
from cryptography.fernet import Fernet


def _settings(monkeypatch: pytest.MonkeyPatch, *, pool_size: str = "3") -> Settings:
    values = {
        "API_KEY": "test-api-key",
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
        "REDIS_URL": "redis://:pass@localhost/0",
        "DB_POOL_SIZE": pool_size,
        "DB_MAX_OVERFLOW": "4",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_create_engine_uses_pool_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    engine = create_engine(settings)
    assert engine.sync_engine.pool.size() == 3
    assert engine.sync_engine.pool._max_overflow == 4
    asyncio.run(engine.dispose())


def test_cached_engine_and_session_factory_use_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings(monkeypatch, pool_size="2")
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    factory = get_session_factory()
    assert factory.kw["expire_on_commit"] is False
    assert factory.kw["bind"].sync_engine.pool.size() == 2
    asyncio.run(factory.kw["bind"].dispose())
    get_session_factory.cache_clear()
    get_engine.cache_clear()


def test_get_session_yields_and_closes_session(monkeypatch: pytest.MonkeyPatch) -> None:
    class SessionContext:
        closed = False
        session = object()

        async def __aenter__(self) -> SessionContext:
            return self

        async def __aexit__(self, *args: object) -> None:
            self.closed = True

    context = SessionContext()
    monkeypatch.setattr(deps, "get_session_factory", lambda: lambda: context)

    async def consume() -> object:
        request = type(
            "Req",
            (),
            {
                "app": type(
                    "App",
                    (),
                    {
                        "state": type(
                            "State",
                            (),
                            {"session_factory": staticmethod(lambda: context)},
                        )()
                    },
                )()
            },
        )()
        generator = deps.get_session(request)
        session = await anext(generator)
        await generator.aclose()
        assert context.closed is True
        return session

    assert asyncio.run(consume()) is context


def test_agent_secret_uses_fernet_ciphertext() -> None:
    key = Fernet.generate_key().decode()
    plaintext = "agent-signing-secret"
    ciphertext = encrypt_agent_secret(plaintext, key)
    assert plaintext not in ciphertext
    assert decrypt_agent_secret(ciphertext, key) == plaintext


def test_secret_helpers_read_only_encryption_key_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    monkeypatch.delenv("API_KEY", raising=False)
    secret = encrypt_agent_secret("standalone-secret")
    assert decrypt_agent_secret(secret) == "standalone-secret"


def test_bulk_step_batch_limit_is_enforced_before_database_use() -> None:
    events = [
        StepEvent(
            seq=seq,
            type="tool",
            started_at="2026-11-14T00:00:00Z",
            duration_ms=0,
            ok=True,
            payload={},
        )
        for seq in range(101)
    ]
    with pytest.raises(ValueError, match="100 events"):
        asyncio.run(bulk_insert_steps(None, uuid4(), events))  # type: ignore[arg-type]
