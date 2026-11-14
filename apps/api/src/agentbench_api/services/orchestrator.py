"""Benchmark creation and run scheduling service."""

from __future__ import annotations

import random
from typing import Any
from uuid import UUID, uuid4

from agentbench_tasks.loader import Suite, task_digest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.models import Agent, Benchmark, Run
from agentbench_api.repositories import upsert_tasks

MAX_RUNS_PER_BENCHMARK = 5_000
MAX_AGENT_IDS = 200


class BenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str = Field(min_length=1, max_length=100)
    agent_ids: list[UUID] = Field(min_length=1, max_length=MAX_AGENT_IDS)
    repetitions: int = Field(default=1, ge=1, le=1000)
    fault_flags: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)


async def create_benchmark(
    session: AsyncSession,
    suite_id: str,
    agent_ids: list[UUID],
    *,
    repetitions: int = 1,
    fault_flags: dict[str, Any] | None = None,
    seed: int | None = None,
    suites: dict[str, Suite] | None = None,
) -> Benchmark:
    """Validate suite and agent configuration and enqueue a benchmark."""
    if not agent_ids:
        raise ValueError("at least one agent is required")
    if repetitions < 1 or repetitions > 1000:
        raise ValueError("repetitions must be between 1 and 1000")
    if len(agent_ids) > MAX_AGENT_IDS:
        raise ValueError("benchmark agent limit exceeded")
    if suites is None:
        raise ValueError("suite registry is required to create benchmarks")
    suite = suites.get(suite_id)
    if suite is None:
        raise ValueError(f"suite {suite_id!r} was not found")
    try:
        await upsert_tasks(session, suite)
    except ValueError:
        raise
    if not suite.tasks:
        raise ValueError(f"suite {suite_id!r} contains no tasks")

    run_count = len(suite.tasks) * len(agent_ids) * repetitions
    if run_count > MAX_RUNS_PER_BENCHMARK:
        raise ValueError(
            "benchmark run count exceeds the configured limit "
            f"({MAX_RUNS_PER_BENCHMARK})"
        )

    agent_rows = list(
        (await session.scalars(select(Agent).where(Agent.id.in_(agent_ids)))).all()
    )
    existing_ids = {agent.id for agent in agent_rows}
    missing = sorted(
        str(agent_id) for agent_id in agent_ids if agent_id not in existing_ids
    )
    if missing:
        raise ValueError(f"unknown agents: {', '.join(missing)}")

    benchmark = Benchmark(
        id=uuid4(),
        suite_id=suite_id,
        agent_ids=list(agent_ids),
        repetitions=repetitions,
        fault_flags=fault_flags or {},
        status="queued",
        seed=seed if seed is not None else random.randrange(0, 2**63),
    )
    session.add(benchmark)
    await session.flush()

    for task in suite.tasks:
        for agent_id in agent_ids:
            for attempt_no in range(1, repetitions + 1):
                session.add(
                    Run(
                        benchmark_id=benchmark.id,
                        agent_id=agent_id,
                        task_id=task.id,
                        task_digest=task_digest(task),
                        attempt_no=attempt_no,
                        status="queued",
                        fault_plan=fault_flags or {},
                    )
                )
    await session.commit()
    await session.refresh(benchmark)
    return benchmark


async def enqueue_benchmark_runs(
    benchmark_id: UUID,
    run_ids: list[UUID],
    *,
    redis_client: Any | None = None,
) -> int:
    if redis_client is None:
        return 0
    for run_id in run_ids:
        await redis_client.lpush("run:queue", str(run_id))
    return len(run_ids)


async def finalize_benchmark(
    benchmark_id: UUID,
    *,
    session_factory: Any | None = None,
) -> dict[str, Any]:
    from agentbench_api.services.runner import (
        finalize_benchmark as runner_finalize_benchmark,
    )

    return await runner_finalize_benchmark(
        benchmark_id,
        session_factory=session_factory,
    )
