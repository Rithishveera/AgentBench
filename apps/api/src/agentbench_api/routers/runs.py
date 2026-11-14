"""Run and step read endpoints with keyset pagination."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.deps import get_session
from agentbench_api.models import Run, Step
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
    statement = (
        select(Step)
        .where(Step.run_id == run_id, Step.seq > after_seq)
        .order_by(Step.seq)
        .limit(limit + 1)
    )
    rows = list((await session.scalars(statement)).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "items": [
            {
                "seq": row.seq,
                "type": row.type,
                "started_at": row.started_at,
                "duration_ms": row.duration_ms,
                "ok": row.ok,
                "payload": row.payload,
                "truncated": row.truncated,
            }
            for row in page
        ],
        "next_cursor": page[-1].seq if has_more and page else None,
    }
