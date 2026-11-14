"""Run and step read endpoints with keyset pagination."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.deps import get_session
from agentbench_api.models import FaultEvent, Run, Step
from agentbench_api.security.auth import require_api_key

router = APIRouter(prefix="/runs", tags=["runs"])
ApiKey = Annotated[None, Depends(require_api_key)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/{run_id}")
async def get_run(run_id: UUID, session: Session, _: ApiKey) -> dict[str, object]:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run.id,
        "benchmark_id": run.benchmark_id,
        "agent_id": run.agent_id,
        "task_id": run.task_id,
        "task_digest": run.task_digest,
        "attempt_no": run.attempt_no,
        "status": run.status,
        "artifact": run.artifact,
        "verdict": run.verdict,
        "failure_cause": run.failure_cause,
        "steps_count": run.steps_count,
        "tool_calls": run.tool_calls,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "cost_usd": run.cost_usd,
        "duration_ms": run.duration_ms,
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


@router.get("/{run_id}/steps")
async def get_run_steps(
    run_id: UUID,
    session: Session,
    _: ApiKey,
    after_seq: Annotated[int, Query(ge=-1)] = -1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    if await session.get(Run, run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    short_label = func.substr(
        case(
            (
                Step.type == "llm",
                func.coalesce(Step.payload["model"].as_string(), "LLM request"),
            ),
            (
                Step.type == "tool",
                func.coalesce(Step.payload["name"].as_string(), "Tool call"),
            ),
            (
                Step.type == "retry",
                func.coalesce(Step.payload["reason"].as_string(), "Retry"),
            ),
            else_="Step",
        ),
        1,
        96,
    ).label("short_label")
    statement = (
        select(
            Step.seq,
            Step.type,
            Step.started_at,
            Step.duration_ms,
            Step.ok,
            short_label,
            Step.truncated,
        )
        .where(Step.run_id == run_id, Step.seq > after_seq)
        .order_by(Step.seq)
        .limit(limit + 1)
    )
    rows = list((await session.execute(statement)).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "items": [
            {
                "seq": row[0],
                "type": row[1],
                "ts": row[2],
                "duration_ms": row[3],
                "ok": row[4],
                "short_label": row[5],
                "truncated": row[6],
            }
            for row in page
        ],
        "next_cursor": page[-1][0] if has_more and page else None,
    }


@router.get("/{run_id}/steps/{seq}")
async def get_run_step(
    run_id: UUID,
    seq: int,
    session: Session,
    _: ApiKey,
) -> dict[str, object]:
    if await session.get(Run, run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    row = await session.get(Step, (run_id, seq))
    if row is None:
        raise HTTPException(status_code=404, detail="Step not found")
    return {
        "seq": row.seq,
        "type": row.type,
        "ts": row.started_at,
        "duration_ms": row.duration_ms,
        "ok": row.ok,
        "payload": row.payload,
        "truncated": row.truncated,
    }


@router.get("/{run_id}/faults")
async def get_run_faults(
    run_id: UUID,
    session: Session,
    _: ApiKey,
    after_seq: Annotated[int, Query(ge=-1)] = -1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    if await session.get(Run, run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    statement = (
        select(
            FaultEvent.seq,
            FaultEvent.fault_type,
            FaultEvent.ts,
            FaultEvent.agent_reaction,
            FaultEvent.detail,
        )
        .where(FaultEvent.run_id == run_id, FaultEvent.seq > after_seq)
        .order_by(FaultEvent.seq)
        .limit(limit + 1)
    )
    rows = list((await session.execute(statement)).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "items": [
            {
                "seq": row[0],
                "fault_type": row[1],
                "ts": row[2],
                "agent_reaction": row[3],
                "detail": row[4],
            }
            for row in page
        ],
        "next_cursor": page[-1][0] if has_more and page else None,
    }
