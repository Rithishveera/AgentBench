from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from agentbench_api.crypto import decrypt_agent_secret, encrypt_agent_secret
from agentbench_api.models import Agent, Benchmark, Run, Step, TaskRecord
from agentbench_api.repositories import (
    bulk_insert_steps,
    claim_run,
    mark_run_terminal,
    upsert_tasks,
)
from agentbench_sdk.schemas import StepEvent
from agentbench_tasks.loader import load_suite
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[2]
CODING_SUITE = ROOT / "suites" / "coding"


@pytest.fixture(scope="module")
def database_url() -> str:
    load_dotenv(ROOT / ".env")
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated Postgres test database")
    if not value.startswith("postgresql+asyncpg://"):
        pytest.fail("TEST_DATABASE_URL must use postgresql+asyncpg")
    return value


def _alembic(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module", autouse=True)
def migrated_schema(database_url: str) -> None:
    command.upgrade(_alembic(database_url), "head")


@pytest.fixture
async def session_factory(
    database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _seed_run(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, str, str]:
    agent_id = uuid.uuid4()
    benchmark_id = uuid.uuid4()
    run_id = uuid.uuid4()
    task_id = "db-task-" + uuid.uuid4().hex[:16]
    agent = Agent(
        id=agent_id,
        name="database test agent",
        url="https://agent.example",
        category="coding",
        secret_encrypted="encrypted-test-secret",
    )
    task = TaskRecord(
        id=task_id,
        category="coding",
        version=1,
        digest="a" * 64,
        title="database test task",
        spec={},
    )
    session.add_all([agent, task])
    await session.flush()
    session.add(
        Benchmark(
            id=benchmark_id,
            suite_id="database-test",
            agent_ids=[agent_id],
            repetitions=1,
            fault_flags={},
            status="running",
            seed=1,
        )
    )
    await session.flush()
    session.add(
        Run(
            id=run_id,
            benchmark_id=benchmark_id,
            agent_id=agent_id,
            task_id=task_id,
            task_digest="a" * 64,
            attempt_no=1,
            status="queued",
            fault_plan={},
        )
    )
    await session.commit()
    return run_id, benchmark_id, agent_id, task_id


async def _cleanup(
    session: AsyncSession,
    benchmark_id: uuid.UUID,
    agent_id: uuid.UUID,
    task_id: str,
) -> None:
    await session.execute(delete(Benchmark).where(Benchmark.id == benchmark_id))
    await session.execute(delete(Agent).where(Agent.id == agent_id))
    await session.execute(delete(TaskRecord).where(TaskRecord.id == task_id))
    await session.commit()


async def test_two_concurrent_claims_have_exactly_one_winner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        run_id, benchmark_id, agent_id, task_id = await _seed_run(session)

    async def claim() -> bool:
        async with session_factory() as session:
            result = await claim_run(session, run_id)
            await session.commit()
            return result is not None

    try:
        assert sum(await asyncio.gather(claim(), claim())) == 1
    finally:
        async with session_factory() as session:
            await _cleanup(session, benchmark_id, agent_id, task_id)


async def test_duplicate_bulk_step_insert_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        run_id, benchmark_id, agent_id, task_id = await _seed_run(session)
        events = [
            StepEvent(
                seq=seq,
                type="tool",
                started_at="2026-11-14T00:00:00Z",
                duration_ms=1,
                ok=True,
                payload={"seq": seq},
            )
            for seq in range(2)
        ]
        try:
            assert await bulk_insert_steps(session, run_id, events) == 2
            assert await bulk_insert_steps(session, run_id, events) == 0
            await session.commit()
            count = await session.scalar(
                select(func.count()).select_from(Step).where(Step.run_id == run_id)
            )
            assert count == 2
        finally:
            await _cleanup(session, benchmark_id, agent_id, task_id)


async def test_task_upsert_requires_digest_change_to_bump_version(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    source = CODING_SUITE / "tasks" / "fix-failing-test"
    task_id = "db-task-" + uuid.uuid4().hex[:16]
    task_dir = tmp_path / "tasks" / task_id
    task_dir.parent.mkdir()
    shutil.copytree(source, task_dir)
    task_yaml = task_dir / "task.yaml"
    spec: dict[str, Any] = yaml.safe_load(task_yaml.read_text(encoding="utf-8"))
    spec["id"] = task_id
    task_yaml.write_text(yaml.safe_dump(spec), encoding="utf-8")
    suite_root = tmp_path / "suite"
    suite_root.mkdir()
    (suite_root / "suite.yaml").write_text("{}\n", encoding="utf-8")
    (suite_root / "tasks").mkdir()
    shutil.move(str(task_dir), str(suite_root / "tasks" / task_id))
    task_yaml = suite_root / "tasks" / task_id / "task.yaml"
    suite = load_suite(suite_root)

    async with session_factory() as session:
        try:
            assert await upsert_tasks(session, suite) == 1
            await session.commit()
            updated_spec = yaml.safe_load(task_yaml.read_text(encoding="utf-8"))
            updated_spec["title"] = "Changed without version bump"
            task_yaml.write_text(yaml.safe_dump(updated_spec), encoding="utf-8")
            with pytest.raises(ValueError, match="without a version bump"):
                await upsert_tasks(session, load_suite(suite_root))
            await session.rollback()
            updated_spec["version"] = 2
            task_yaml.write_text(yaml.safe_dump(updated_spec), encoding="utf-8")
            assert await upsert_tasks(session, load_suite(suite_root)) == 1
            await session.commit()
            task = await session.get(TaskRecord, task_id)
            assert task is not None
            assert task.version == 2
        finally:
            await session.execute(delete(TaskRecord).where(TaskRecord.id == task_id))
            await session.commit()


async def test_agent_secret_roundtrips_as_ciphertext(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    key = Fernet.generate_key().decode()
    plaintext = "agent-secret-" + uuid.uuid4().hex
    encrypted = encrypt_agent_secret(plaintext, key)
    agent_id = uuid.uuid4()
    async with session_factory() as session:
        try:
            session.add(
                Agent(
                    id=agent_id,
                    name="secret test agent",
                    url="https://agent.example",
                    category="coding",
                    secret_encrypted=encrypted,
                )
            )
            await session.commit()
            stored = await session.get(Agent, agent_id)
            assert stored is not None
            assert plaintext not in stored.secret_encrypted
            assert decrypt_agent_secret(stored.secret_encrypted, key) == plaintext
        finally:
            await session.execute(delete(Agent).where(Agent.id == agent_id))
            await session.commit()


async def test_step_order_query_uses_composite_primary_key(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        run_id, benchmark_id, agent_id, task_id = await _seed_run(session)
        try:
            await session.execute(text("SET LOCAL enable_seqscan = off"))
            result = await session.execute(
                text(
                    "EXPLAIN SELECT seq FROM step WHERE run_id = :run_id ORDER BY seq"
                ),
                {"run_id": run_id},
            )
            plan = "\n".join(row[0] for row in result.all())
            assert "step_pkey" in plan
            assert "Seq Scan" not in plan
        finally:
            await _cleanup(session, benchmark_id, agent_id, task_id)


async def test_mark_run_terminal_sets_verdict_only_for_completed_runs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        run_id, benchmark_id, agent_id, task_id = await _seed_run(session)
        try:
            assert await claim_run(session, run_id) is not None
            await session.commit()
            with pytest.raises(ValueError, match="only completed"):
                await mark_run_terminal(
                    session,
                    run_id,
                    "timeout",
                    verdict={"passed": False},
                )
            assert await mark_run_terminal(
                session,
                run_id,
                "completed",
                verdict={"passed": True, "score": 1},
                artifact={"patch": "diff"},
                duration_ms=25,
            )
            await session.commit()
            run = await session.get(Run, run_id)
            assert run is not None
            assert run.verdict == {"passed": True, "score": 1}
            assert run.status == "completed"
        finally:
            await _cleanup(session, benchmark_id, agent_id, task_id)
