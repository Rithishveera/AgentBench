from __future__ import annotations

import asyncio
import hashlib
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from agentbench_api.config import Settings
from agentbench_api.db import get_session_factory
from agentbench_api.main import create_app
from agentbench_api.models import Run


@asynccontextmanager
async def _noop_lifespan(app):
    yield


class FakeRedis:
    async def aclose(self) -> None:
        return None

    async def lpush(self, *args, **kwargs):
        return 1


class FakeSession:
    def __init__(self, *, data: list[Run] | None = None) -> None:
        self.data = data or []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, *args, **kwargs) -> None:
        return None

    def add(self, value: object) -> None:
        self.data.append(value)

    async def execute(self, *args, **kwargs):
        class Result:
            def scalar_one_or_none(self):
                return object()
            def scalars(self):
                class Rows:
                    def all(self):
                        return [0]
                return Rows()
        return Result()

    async def get(self, model, key):
        for item in self.data:
            if getattr(item, "id", None) == key:
                return item
        return None

    async def scalars(self, *args, **kwargs):
        class Rows:
            def all(self):
                return []
        return Rows()

    async def scalar(self, *args, **kwargs):
        return None

    async def delete(self, *args, **kwargs) -> None:
        return None

    async def rollback(self) -> None:
        return None

    def begin_nested(self):
        class Nested:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return None
        return Nested()


@pytest.fixture
def app() -> object:
    os.environ["API_KEY"] = "api-key"
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://agentbench:pw@localhost/agentbench"
    os.environ["REDIS_URL"] = "redis://:pw@localhost:6379/0"
    settings = Settings(_env_file=None)
    app = create_app(settings, session_factory=lambda: FakeSession(), redis_client=FakeRedis())
    return app


@pytest.mark.asyncio
async def test_wrong_or_missing_api_key_is_rejected() -> None:
    settings = Settings(
        API_KEY="api-key",
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        DATABASE_URL="postgresql+asyncpg://agentbench:pw@localhost/agentbench",
        REDIS_URL="redis://:pw@localhost:6379/0",
        _env_file=None,
    )
    app = create_app(settings)
    app.router.lifespan_context = _noop_lifespan
    app.state.session_factory = lambda: FakeSession()
    app.state.redis = FakeRedis()
    app.state.settings = settings
    client = TestClient(app)
    no_key = client.get("/suites")
    bad_key = client.get("/suites", headers={"X-API-Key": "wrong"})
    assert no_key.status_code == 401
    assert bad_key.status_code == 401


@pytest.mark.asyncio
async def test_run_token_must_match_run_and_not_expire() -> None:
    settings = Settings(
        API_KEY="api-key",
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        DATABASE_URL="postgresql+asyncpg://agentbench:pw@localhost/agentbench",
        REDIS_URL="redis://:pw@localhost:6379/0",
        _env_file=None,
    )
    run_id = uuid4()
    other_id = uuid4()
    run_rows = [
        Run(
            id=run_id,
            benchmark_id=uuid4(),
            agent_id=uuid4(),
            task_id="task-1",
            task_digest="a" * 64,
            attempt_no=1,
            status="running",
            fault_plan={},
            token_hash=hashlib.sha256("token-abc".encode()).hexdigest(),
            token_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
        Run(
            id=other_id,
            benchmark_id=uuid4(),
            agent_id=uuid4(),
            task_id="task-2",
            task_digest="b" * 64,
            attempt_no=1,
            status="running",
            fault_plan={},
            token_hash=hashlib.sha256("other".encode()).hexdigest(),
            token_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
        Run(
            id=uuid4(),
            benchmark_id=uuid4(),
            agent_id=uuid4(),
            task_id="task-3",
            task_digest="c" * 64,
            attempt_no=1,
            status="running",
            fault_plan={},
            token_hash=hashlib.sha256("expired".encode()).hexdigest(),
            token_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        ),
    ]
    app = create_app(settings)
    app.router.lifespan_context = _noop_lifespan
    app.state.session_factory = lambda: FakeSession(data=run_rows)
    app.state.redis = FakeRedis()
    app.state.settings = settings
    client = TestClient(app)
    with client as test_client:
        test_client.app.state.suites = {}
        response = test_client.post(
            f"/internal/runs/{run_id}/steps",
            headers={"Authorization": "Bearer token-abc", "X-API-Key": "api-key"},
            json=[{"seq": 0, "type": "tool", "started_at": "2026-11-14T00:00:00Z", "duration_ms": 2, "ok": True, "payload": {"x": 1}}],
        )
        wrong_run = test_client.post(
            f"/internal/runs/{other_id}/steps",
            headers={"Authorization": "Bearer token-abc", "X-API-Key": "api-key"},
            json=[{"seq": 0, "type": "tool", "started_at": "2026-11-14T00:00:00Z", "duration_ms": 2, "ok": True, "payload": {"x": 1}}],
        )
        expired_response = test_client.post(
            f"/internal/runs/{run_rows[2].id}/steps",
            headers={"Authorization": "Bearer expired", "X-API-Key": "api-key"},
            json=[{"seq": 0, "type": "tool", "started_at": "2026-11-14T00:00:00Z", "duration_ms": 2, "ok": True, "payload": {"x": 1}}],
        )
        assert response.status_code == 204
        assert wrong_run.status_code == 403
        assert expired_response.status_code == 403


@pytest.mark.asyncio
async def test_complete_on_non_running_run_is_conflict() -> None:
    os.environ["API_KEY"] = "api-key"
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://agentbench:pw@localhost/agentbench"
    os.environ["REDIS_URL"] = "redis://:pw@localhost:6379/0"
    settings = Settings(_env_file=None)
    completed_run = Run(
        id=uuid4(),
        benchmark_id=uuid4(),
        agent_id=uuid4(),
        task_id="task-1",
        task_digest="a" * 64,
        attempt_no=1,
        status="completed",
        fault_plan={},
        token_hash=hashlib.sha256("token-ok".encode()).hexdigest(),
        token_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        verdict={"passed": True},
    )
    app = create_app(settings)
    app.router.lifespan_context = _noop_lifespan
    app.state.session_factory = lambda: FakeSession(data=[completed_run])
    app.state.redis = FakeRedis()
    app.state.settings = settings
    client = TestClient(app)
    response = client.post(
        f"/internal/runs/{completed_run.id}/complete",
        headers={"Authorization": "Bearer token-ok", "X-API-Key": "api-key"},
        json={"status": "success", "answer": "done"},
    )
    assert response.status_code == 409
