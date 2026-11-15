"""Per-run callback endpoints for agent step and completion events."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from agentbench_sdk.schemas import CompleteRequest, StepEvent
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.deps import get_session
from agentbench_api.models import Run
from agentbench_api.repositories import bulk_insert_steps, mark_run_terminal
from agentbench_api.security.auth import require_run_token
from agentbench_api.security.redact import redact_payload

router = APIRouter(tags=["internal"])
Session = Annotated[AsyncSession, Depends(get_session)]
RunToken = Annotated[Run, Depends(require_run_token)]
StepBatch = Annotated[list[StepEvent], Body(max_length=100)]


@router.get("/health")
async def internal_health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/runs/{run_id}/steps", status_code=204)
async def ingest_steps(
    run_id: UUID,
    events: StepBatch,
    request: Request,
    run: RunToken,
    session: Session,
) -> Response:
    if run.artifact is not None:
        raise HTTPException(status_code=409, detail="Run callback is already complete")
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    settings = request.app.state.settings
    secrets = (
        token,
        settings.api_key.get_secret_value(),
        settings.encryption_key.get_secret_value(),
    )
    unique_events: dict[int, StepEvent] = {}
    for event in events:
        payload, truncated = redact_payload(event.payload, secrets)
        unique_events.setdefault(
            event.seq,
            event.model_copy(
                update={"payload": payload, "truncated": event.truncated or truncated}
            ),
        )
    ordered_events = [unique_events[seq] for seq in sorted(unique_events)]
    inserted = await bulk_insert_steps(session, run_id, ordered_events)
    result = await session.execute(
        update(Run)
        .where(Run.id == run_id, Run.status == "running", Run.artifact.is_(None))
        .values(last_event_at=func.now(), steps_count=Run.steps_count + inserted)
        .returning(Run.id)
    )
    if result.scalar_one_or_none() is None:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Run callback is no longer active")
    await session.commit()
    return Response(status_code=204)


@router.post("/runs/{run_id}/complete", status_code=204)
async def complete_run(
    run_id: UUID,
    body: CompleteRequest,
    request: Request,
    run: RunToken,
    session: Session,
) -> Response:
    if run.artifact is not None or run.status != "running":
        raise HTTPException(status_code=409, detail="Run is not accepting completion")
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    settings = request.app.state.settings
    artifact = None
    if body.status == "success":
        artifact, _ = redact_payload(
            {"patch": body.patch, "answer": body.answer},
            (
                token,
                settings.api_key.get_secret_value(),
                settings.encryption_key.get_secret_value(),
            ),
        )
        result = await session.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "running", Run.artifact.is_(None))
            .values(artifact=artifact, last_event_at=func.now())
            .returning(Run.id)
        )
        if result.scalar_one_or_none() is None:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Run completion was already received",
            )
    else:
        completed = await mark_run_terminal(
            session,
            run_id,
            "agent_error",
            failure_cause="agent_error",
            error=body.error,
        )
        if not completed:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Run completion was already received",
            )
    await session.commit()
    await request.app.state.redis.lpush(f"run:{run_id}:done", str(run_id))
    # Publish the status transition to the benchmark hub.
    if body.status != "success":
        from agentbench_api.ws.hub import publish as hub_publish
        await hub_publish(
            request.app.state.redis,
            run.benchmark_id,
            {
                "type": "run_update",
                "run_id": str(run_id),
                "agent_id": str(run.agent_id),
                "task_id": run.task_id,
                "status": "agent_error",
            },
        )
    return Response(status_code=204)
