"""Benchmark orchestration endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from agentbench_tasks.loader import Suite
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.deps import get_session
from agentbench_api.models import Benchmark, Run
from agentbench_api.security.auth import require_api_key
from agentbench_api.services.orchestrator import BenchmarkRequest, create_benchmark

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])
ApiKey = Annotated[None, Depends(require_api_key)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/{benchmark_id}")
async def get_benchmark(
    benchmark_id: UUID,
    _: ApiKey,
    session: Session,
) -> dict[str, object]:
    benchmark = await session.get(Benchmark, benchmark_id)
    if benchmark is None:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return {
        "id": benchmark.id,
        "status": benchmark.status,
        "suite_id": benchmark.suite_id,
        "repetitions": benchmark.repetitions,
        "agent_ids": benchmark.agent_ids,
        "summary": benchmark.summary,
        "seed": benchmark.seed,
        "created_at": benchmark.created_at,
        "finished_at": benchmark.finished_at,
    }


@router.get("/{benchmark_id}/runs")
async def list_benchmark_runs(
    benchmark_id: UUID,
    _: ApiKey,
    session: Session,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    if await session.get(Benchmark, benchmark_id) is None:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    statement = (
        select(
            Run.id,
            Run.agent_id,
            Run.task_id,
            Run.attempt_no,
            Run.fault_mode,
            Run.status,
            Run.verdict,
            Run.failure_cause,
            Run.duration_ms,
            Run.cost_usd,
            Run.started_at,
            Run.finished_at,
        )
        .where(Run.benchmark_id == benchmark_id)
        .order_by(Run.id)
        .limit(limit + 1)
    )
    if cursor is not None:
        statement = statement.where(Run.id > cursor)
    rows = list((await session.execute(statement)).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    fields = (
        "id",
        "agent_id",
        "task_id",
        "attempt_no",
        "fault_mode",
        "status",
        "verdict",
        "failure_cause",
        "duration_ms",
        "cost_usd",
        "started_at",
        "finished_at",
    )
    return {
        "items": [dict(zip(fields, row, strict=True)) for row in page],
        "next_cursor": str(page[-1][0]) if has_more and page else None,
    }


@router.post("", status_code=202)
async def create_benchmark_route(
    body: BenchmarkRequest,
    request: Request,
    session: Session,
    _: ApiKey,
) -> dict[str, object]:
    suites: dict[str, Suite] = request.app.state.suites
    benchmark = await create_benchmark(
        session,
        body.suite_id,
        list(body.agent_ids),
        repetitions=body.repetitions,
        fault_flags=body.fault_flags,
        paired=body.paired,
        seed=body.seed,
        suites=suites,
    )
    run_ids = [
        row.id
        for row in (
            await session.scalars(select(Run).where(Run.benchmark_id == benchmark.id))
        ).all()
    ]
    await request.app.state.redis.lpush(
        "run:queue",
        *[str(run_id) for run_id in run_ids],
    )
    response: dict[str, object] = {
        "id": benchmark.id,
        "status": benchmark.status,
        "run_count": len(run_ids),
        "suite_id": benchmark.suite_id,
    }
    if benchmark.paired:
        response["warning"] = (
            "Paired mode doubles the intended benchmark spend because each run is "
            "executed once as a baseline and once with injected faults."
        )
        response["estimated_spend_multiplier"] = 2.0
        response["estimated_spend_usd"] = round(len(run_ids) * 0.05, 2)
    return response
