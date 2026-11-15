"""Tests for WS ticket issuance, verification, snapshot building, and hub registry."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from agentbench_api.config import Settings
from agentbench_api.main import create_app
from agentbench_api.models import Benchmark
from agentbench_api.ws.hub import HubRegistry, channel
from agentbench_api.ws.snapshot import build_snapshot
from agentbench_api.ws.tickets import consume_ticket, create_ticket
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@asynccontextmanager
async def _noop_lifespan(app: Any) -> Any:
    yield


class FakeRedis:
    """Minimal Redis fake for ticket and pub/sub tests."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def aclose(self) -> None:
        pass

    async def lpush(self, *args: Any, **kwargs: Any) -> int:
        return 1

    async def set(self, key: str, value: str, *, ex: int = 0) -> None:
        self._store[key] = value

    async def getdel(self, key: str) -> str | None:
        return self._store.pop(key, None)

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def publish(self, *args: Any, **kwargs: Any) -> int:
        return 0


class FakeSession:
    """Minimal async session fake."""

    def __init__(self, *, data: list[Any] | None = None) -> None:
        self.data: list[Any] = data or []

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, *_: Any) -> None:
        pass

    def add(self, value: Any) -> None:
        self.data.append(value)

    async def execute(self, *_: Any, **__: Any) -> Any:
        class _Rows:
            def all(self) -> list[Any]:
                return []

            def scalars(self) -> Any:
                class _S:
                    def all(self) -> list[Any]:
                        return []

                return _S()

        return _Rows()

    async def get(self, model: type[Any], key: Any) -> Any:
        for item in self.data:
            if getattr(item, "id", None) == key:
                return item
        return None

    async def scalars(self, *_: Any, **__: Any) -> Any:
        class _S:
            def all(self) -> list[Any]:
                return []

        return _S()

    async def scalar(self, *_: Any, **__: Any) -> None:
        return None

    async def delete(self, *_: Any) -> None:
        pass

    async def rollback(self) -> None:
        pass

    def begin_nested(self) -> Any:
        class _N:
            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *_: Any) -> None:
                pass

        return _N()


def _make_app(session_data: list[Any] | None = None) -> Any:
    os.environ.setdefault("API_KEY", "api-key")
    os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    settings = Settings(_env_file=None)
    redis = FakeRedis()
    data = session_data or []
    app = create_app(
        settings,
        session_factory=lambda: FakeSession(data=data),  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
    )
    app.router.lifespan_context = _noop_lifespan
    app.state.session_factory = lambda: FakeSession(data=data)
    app.state.redis = redis
    app.state.settings = settings
    app.state.suites = {}
    return app


# ---------------------------------------------------------------------------
# Ticket unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_consume_ticket() -> None:
    redis = FakeRedis()
    benchmark_id = uuid4()
    token = await create_ticket(redis, benchmark_id)  # type: ignore[arg-type]
    assert token
    assert await consume_ticket(redis, token, benchmark_id) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_ticket_single_use() -> None:
    redis = FakeRedis()
    benchmark_id = uuid4()
    token = await create_ticket(redis, benchmark_id)  # type: ignore[arg-type]
    await consume_ticket(redis, token, benchmark_id)  # type: ignore[arg-type]
    assert await consume_ticket(redis, token, benchmark_id) is False  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_ticket_wrong_benchmark_rejected() -> None:
    redis = FakeRedis()
    benchmark_id = uuid4()
    token = await create_ticket(redis, benchmark_id)  # type: ignore[arg-type]
    assert await consume_ticket(redis, token, uuid4()) is False  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_ticket_missing_rejected() -> None:
    redis = FakeRedis()
    assert await consume_ticket(redis, "nonexistent", uuid4()) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# stream-ticket HTTP endpoint
# ---------------------------------------------------------------------------


def test_issue_stream_ticket_requires_api_key() -> None:
    benchmark_id = uuid4()
    benchmark = Benchmark(
        id=benchmark_id,
        suite_id="s",
        agent_ids=[],
        repetitions=1,
        fault_flags={},
        status="running",
        seed=42,
    )
    app = _make_app(session_data=[benchmark])
    client = TestClient(app)
    resp = client.post(f"/benchmarks/{benchmark_id}/stream-ticket")
    assert resp.status_code == 401


def test_issue_stream_ticket_404_on_unknown_benchmark() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        f"/benchmarks/{uuid4()}/stream-ticket",
        headers={"X-API-Key": "api-key"},
    )
    assert resp.status_code == 404


def test_issue_stream_ticket_returns_token() -> None:
    benchmark_id = uuid4()
    benchmark = Benchmark(
        id=benchmark_id,
        suite_id="s",
        agent_ids=[],
        repetitions=1,
        fault_flags={},
        status="running",
        seed=42,
    )
    app = _make_app(session_data=[benchmark])
    client = TestClient(app)
    resp = client.post(
        f"/benchmarks/{benchmark_id}/stream-ticket",
        headers={"X-API-Key": "api-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "ticket" in body
    assert len(body["ticket"]) > 10


# ---------------------------------------------------------------------------
# Hub channel naming
# ---------------------------------------------------------------------------


def test_hub_channel_is_deterministic() -> None:
    bid = uuid4()
    assert channel(bid) == f"bench:{bid}"


# ---------------------------------------------------------------------------
# Snapshot unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_snapshot_missing_benchmark() -> None:
    session = FakeSession()
    result = await build_snapshot(session, uuid4())  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_build_snapshot_includes_benchmark_and_runs() -> None:
    benchmark_id = uuid4()
    benchmark = Benchmark(
        id=benchmark_id,
        suite_id="s",
        agent_ids=[],
        repetitions=1,
        fault_flags={},
        status="running",
        seed=42,
    )

    class _SessionWithBenchmark(FakeSession):
        async def get(self, model: type[Any], key: Any) -> Any:
            if model is Benchmark and key == benchmark_id:
                return benchmark
            return None

        async def execute(self, *_: Any, **__: Any) -> Any:
            class _R:
                def all(self) -> list[Any]:
                    return []

            return _R()

    result = await build_snapshot(_SessionWithBenchmark(), benchmark_id)  # type: ignore[arg-type]
    assert result is not None
    assert result["type"] == "snapshot"
    assert result["benchmark"]["id"] == str(benchmark_id)
    assert result["benchmark"]["status"] == "running"
    assert result["runs"] == []


# ---------------------------------------------------------------------------
# Hub registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hub_registry_returns_same_hub() -> None:
    reg = HubRegistry()
    redis = FakeRedis()
    bid = uuid4()
    h1 = await reg.get(redis, bid)  # type: ignore[arg-type]
    h2 = await reg.get(redis, bid)  # type: ignore[arg-type]
    assert h1 is h2


@pytest.mark.asyncio
async def test_hub_registry_different_benchmark_ids() -> None:
    reg = HubRegistry()
    redis = FakeRedis()
    h1 = await reg.get(redis, uuid4())  # type: ignore[arg-type]
    h2 = await reg.get(redis, uuid4())  # type: ignore[arg-type]
    assert h1 is not h2
