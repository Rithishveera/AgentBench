"""Concurrency-safe persistence operations for benchmark runs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from agentbench_sdk.schemas import StepEvent
from agentbench_tasks.loader import Suite, task_digest
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.models import Run, Step, TaskRecord

TerminalRunStatus = Literal["completed", "agent_error", "timeout", "infra_error"]
MAX_STEP_BATCH = 100


def _started_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


async def upsert_tasks(session: AsyncSession, suite: Suite) -> int:
    tasks = suite.tasks
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("suite contains duplicate task IDs")
    if not tasks:
        return 0

    rows = [
        {
            "id": task.id,
            "category": task.category,
            "version": task.version,
            "digest": task_digest(task),
            "title": task.title,
            "spec": task.model_dump(mode="json"),
        }
        for task in tasks
    ]
    statement = insert(TaskRecord).values(rows)
    same_version = and_(
        TaskRecord.version == statement.excluded.version,
        TaskRecord.digest == statement.excluded.digest,
    )
    bumped_version = TaskRecord.version < statement.excluded.version
    async with session.begin_nested():
        result = await session.execute(
            statement.on_conflict_do_update(
                index_elements=[TaskRecord.id],
                set_={
                    "category": statement.excluded.category,
                    "version": statement.excluded.version,
                    "digest": statement.excluded.digest,
                    "title": statement.excluded.title,
                    "spec": statement.excluded.spec,
                },
                where=or_(same_version, bumped_version),
            ).returning(TaskRecord.id)
        )
        persisted = set(result.scalars().all())
        if persisted != set(ids):
            existing = await session.execute(
                select(TaskRecord.id, TaskRecord.version).where(
                    TaskRecord.id.in_(set(ids) - persisted)
                )
            )
            versions = dict(existing.all())
            task_by_id = {task.id: task for task in tasks}
            for task_id, stored_version in versions.items():
                task = task_by_id[task_id]
                if task.version == stored_version:
                    raise ValueError(
                        f"task {task_id} digest changed without a version bump"
                    )
                raise ValueError(f"task {task_id} version must increase")
            raise ValueError("task upsert did not persist every task")
    return len(persisted)


async def claim_run(session: AsyncSession, run_id: UUID) -> Run | None:
    statement = (
        update(Run)
        .where(Run.id == run_id, Run.status == "queued")
        .values(status="running", started_at=func.now(), last_event_at=func.now())
        .returning(Run)
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def bulk_insert_steps(
    session: AsyncSession,
    run_id: UUID,
    events: list[StepEvent],
) -> int:
    if not events:
        return 0
    if len(events) > MAX_STEP_BATCH:
        raise ValueError("step batches cannot exceed 100 events")
    rows = [
        {
            "run_id": run_id,
            "seq": event.seq,
            "type": event.type,
            "started_at": _started_at(event.started_at),
            "duration_ms": event.duration_ms,
            "ok": event.ok,
            "payload": event.payload,
            "truncated": event.truncated,
        }
        for event in events
    ]
    result = await session.execute(
        insert(Step)
        .values(rows)
        .on_conflict_do_nothing(index_elements=[Step.run_id, Step.seq])
        .returning(Step.seq)
    )
    return len(result.scalars().all())


async def mark_run_terminal(
    session: AsyncSession,
    run_id: UUID,
    status: TerminalRunStatus,
    *,
    artifact: dict[str, Any] | None = None,
    verdict: dict[str, Any] | None = None,
    failure_cause: str | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
) -> bool:
    if status != "completed" and verdict is not None:
        raise ValueError("only completed runs may have a verdict")
    if status == "completed" and verdict is None:
        raise ValueError("completed runs require a verdict")
    if duration_ms is not None and duration_ms < 0:
        raise ValueError("duration_ms cannot be negative")
    values: dict[str, Any] = {
        "status": status,
        "artifact": artifact,
        "verdict": verdict,
        "failure_cause": failure_cause,
        "error": error,
        "finished_at": func.now(),
    }
    if duration_ms is not None:
        values["duration_ms"] = duration_ms
    result = await session.execute(
        update(Run)
        .where(Run.id == run_id, Run.status == "running")
        .values(**values)
        .returning(Run.id)
    )
    return result.scalar_one_or_none() is not None
