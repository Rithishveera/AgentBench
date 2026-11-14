"""Run execution and terminalization service."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from agentbench_sdk.client import AgentClient
from agentbench_sdk.schemas import (
    CallbackConfig,
    FileContent,
    RunLimits,
    RunRequest,
    RunTask,
)
from agentbench_tasks.loader import Suite, visible_files
from agentbench_tasks.schema import Task
from agentbench_tasks.validators.base import InfraError
from pydantic import AnyHttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentbench_api.config import Settings
from agentbench_api.crypto import decrypt_agent_secret
from agentbench_api.db import get_session_factory
from agentbench_api.models import Agent, Benchmark, Run, TaskRecord
from agentbench_api.repositories import claim_run, mark_run_terminal
from agentbench_api.services.sandbox import DockerSandbox
from agentbench_api.services.scorer import summarize_runs
from agentbench_api.services.validator import validate_run


async def _task_model(task_record: TaskRecord) -> Task:
    return Task.model_validate(task_record.spec)


async def _run_request_for(
    session: AsyncSession,
    run: Run,
    *,
    suites: dict[str, Suite] | None = None,
) -> tuple[Task, RunRequest]:
    task_record = await session.get(TaskRecord, run.task_id)
    if task_record is None:
        raise ValueError(f"task {run.task_id} was not found")
    task = await _task_model(task_record)
    files: list[FileContent] = []
    if suites is not None:
        for suite in suites.values():
            if any(candidate.id == run.task_id for candidate in suite.tasks):
                for candidate in suite.tasks:
                    if candidate.id == run.task_id:
                        files = [
                            FileContent(path=file["path"], content=file["content"])
                            for file in visible_files(candidate)
                        ]
                        break
                break
    run_limits = RunLimits(**task.limits.model_dump(mode="json"))
    request = RunRequest(
        run_id=str(run.id),
        task=RunTask(
            id=task.id,
            category=task.category,
            prompt=task.prompt,
            files=files,
            limits=run_limits,
        ),
        callback=CallbackConfig(
            base_url=AnyHttpUrl("http://localhost/internal"),
            token="placeholder",
        ),
    )
    return task, request


async def execute_run(
    run_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    redis_client: Any | None = None,
    settings: Settings | None = None,
    suites: dict[str, Suite] | None = None,
) -> bool:
    """Claim a run, start the agent, wait for callback completion, and finalize it."""
    factory = session_factory or get_session_factory()
    settings = settings or Settings()
    async with factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return False
        if run.status == "queued":
            claimed = await claim_run(session, run_id)
            if claimed is None:
                return False
            run = claimed
        if run.status not in {"queued", "running"}:
            return True

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        run.token_hash = token_hash
        run.token_expires_at = datetime.now(UTC) + timedelta(minutes=5)

        agent = await session.get(Agent, run.agent_id)
        if agent is None:
            await mark_run_terminal(
                session,
                run.id,
                "infra_error",
                failure_cause="agent_missing",
                error="agent record was not found",
            )
            await session.commit()
            return False

        task_record = await session.get(TaskRecord, run.task_id)
        if task_record is None:
            await mark_run_terminal(
                session,
                run.id,
                "infra_error",
                failure_cause="task_missing",
                error=f"task {run.task_id} was not found",
            )
            await session.commit()
            return False

        task = await _task_model(task_record)
        _, request = await _run_request_for(session, run, suites=suites)
        request.callback = CallbackConfig(
            base_url=AnyHttpUrl("http://platform.internal/internal"),
            token=token,
        )
        secret = decrypt_agent_secret(agent.secret_encrypted, settings.encryption_key)
        client = AgentClient()
        try:
            await client.start_run(agent.url, secret, request)
        except Exception as exc:
            await mark_run_terminal(
                session,
                run.id,
                "infra_error",
                failure_cause="start_run",
                error=str(exc),
            )
            await session.commit()
            return False
        finally:
            await client.close()

        await session.commit()
        timeout_seconds = max(1, int(task.limits.timeout_s))
        if redis_client is not None:
            while True:
                item = await redis_client.blpop(
                    f"run:{run.id}:done",
                    timeout=timeout_seconds,
                )
                if item is not None:
                    break
                refreshed = await session.get(Run, run.id)
                if refreshed is None or refreshed.status != "running":
                    break
                latest = datetime.now(UTC)
                if (
                    refreshed.last_event_at is not None
                    and refreshed.last_event_at
                    < latest - timedelta(seconds=timeout_seconds)
                ):
                    break
        else:
            await asyncio_sleep(timeout_seconds)
            refreshed = await session.get(Run, run.id)
            if (
                refreshed is not None
                and refreshed.status == "running"
                and refreshed.artifact is None
            ):
                await mark_run_terminal(
                    session,
                    run.id,
                    "timeout",
                    failure_cause="timeout",
                    error="run did not complete before its timeout",
                )
                await session.commit()
                return True

        refreshed = await session.get(Run, run.id)
        if refreshed is None:
            return False
        if refreshed.status in {"agent_error", "timeout", "infra_error"}:
            return True
        if refreshed.status != "running":
            return True
        if refreshed.artifact is None:
            await mark_run_terminal(
                session,
                run.id,
                "timeout",
                failure_cause="timeout",
                error="run timed out before callback completion",
            )
            await session.commit()
            return True

        patch = (refreshed.artifact or {}).get("patch")
        try:
            verdict = await validate_run(
                task,
                (
                    (patch or "").encode("utf-8")
                    if isinstance(patch, str)
                    else (patch or b"")
                ),
                DockerSandbox(),
            )
        except InfraError as exc:
            await mark_run_terminal(
                session,
                run.id,
                "infra_error",
                failure_cause="validator",
                error=str(exc),
            )
            await session.commit()
            return False

        if verdict is None:
            await mark_run_terminal(
                session,
                run.id,
                "infra_error",
                failure_cause="validator",
                error="validator returned no result",
            )
            await session.commit()
            return False

        await mark_run_terminal(
            session,
            run.id,
            "completed",
            verdict=verdict.model_dump(mode="json"),
            artifact=refreshed.artifact,
            duration_ms=max(int(refreshed.duration_ms or 0), 0),
        )
        await session.commit()
        return True


async def finalize_benchmark(
    benchmark_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, Any]:
    """Summarize a benchmark after all child runs are terminal."""
    factory = session_factory or get_session_factory()
    async with factory() as session:
        benchmark = await session.get(Benchmark, benchmark_id)
        if benchmark is None:
            return {"id": str(benchmark_id), "status": "missing"}
        rows = cast(
            Sequence[
                tuple[
                    UUID,
                    str,
                    str,
                    str,
                    dict[str, Any] | None,
                    str | None,
                    int,
                    int,
                    int | None,
                    datetime | None,
                    datetime | None,
                ]
            ],
            (
                await session.execute(
                    select(
                        Run.agent_id,
                        Run.task_id,
                        Run.task_digest,
                        Run.status,
                        Run.verdict,
                        Run.failure_cause,
                        Run.steps_count,
                        Run.tool_calls,
                        Run.duration_ms,
                        Run.started_at,
                        Run.finished_at,
                    ).where(Run.benchmark_id == benchmark_id)
                )
            ).all(),
        )
        status_breakdown = {
            "queued": 0,
            "running": 0,
            "completed": 0,
            "agent_error": 0,
            "timeout": 0,
            "infra_error": 0,
        }
        task_passes: dict[str, dict[str, int]] = {}
        task_digests: dict[str, str] = {}
        agent_runs: dict[str, list[dict[str, Any]]] = {}
        agent_task_passes: dict[str, dict[str, dict[str, int]]] = {}
        run_rows: list[dict[str, Any]] = []
        for (
            run_agent_id,
            task_id,
            task_digest,
            status,
            verdict,
            failure_cause,
            steps_count,
            tool_calls,
            duration_ms,
            _,
            _,
        ) in rows:
            status_breakdown[status] = status_breakdown.get(status, 0) + 1
            run_rows.append(
                {
                    "status": status,
                    "passed": bool(verdict and verdict.get("passed") is True),
                    "failure_cause": failure_cause,
                    "steps_count": steps_count,
                    "tool_calls": tool_calls,
                    "duration_ms": duration_ms,
                }
            )
            task_digests[task_id] = task_digest
            task_entry = task_passes.setdefault(task_id, {"attempts": 0, "passes": 0})
            agent_task_entry = agent_task_passes.setdefault(
                str(run_agent_id), {}
            ).setdefault(task_id, {"attempts": 0, "passes": 0})
            if status in {"completed", "agent_error", "timeout"}:
                task_entry["attempts"] += 1
                agent_task_entry["attempts"] += 1
                if status == "completed" and verdict and verdict.get("passed") is True:
                    task_entry["passes"] += 1
                    agent_task_entry["passes"] += 1
            agent_runs.setdefault(str(run_agent_id), []).append(
                {
                    "status": status,
                    "passed": bool(verdict and verdict.get("passed") is True),
                    "failure_cause": failure_cause,
                    "steps_count": steps_count,
                    "tool_calls": tool_calls,
                    "duration_ms": duration_ms,
                }
            )
        agent_summaries: dict[str, dict[str, Any]] = {}
        for summary_agent_id, agent_run_rows in agent_runs.items():
            summary = summarize_runs(agent_run_rows)
            summary["agent_id"] = summary_agent_id
            summary["task_passes"] = {
                task_id: {
                    "attempts": agent_task_passes[summary_agent_id]
                    .get(task_id, {})
                    .get("attempts", 0),
                    "passes": agent_task_passes[summary_agent_id]
                    .get(task_id, {})
                    .get("passes", 0),
                }
                for task_id in sorted(task_passes)
            }
            agent_summaries[summary_agent_id] = summary
        overall = summarize_runs(run_rows)
        overall["task_passes"] = {
            task_id: {
                "attempts": task_values["attempts"],
                "passes": task_values["passes"],
            }
            for task_id, task_values in sorted(task_passes.items())
        }
        benchmark.summary = {
            "status_breakdown": status_breakdown,
            "overall": overall,
            "agents": agent_summaries,
            "task_passes": overall["task_passes"],
            "task_digests": task_digests,
            "category": next(
                (task_category for task_category in {"coding": "coding"}),
                "coding",
            ),
        }
        if rows and all(
            status in {"completed", "agent_error", "timeout", "infra_error"}
            for _, _, _, status, *_ in rows
        ):
            benchmark.status = "completed"
            benchmark.finished_at = datetime.now(UTC)
        elif rows and any(
            status in {"running", "queued"} for _, _, _, status, *_ in rows
        ):
            benchmark.status = "running"
        else:
            benchmark.status = "queued"
        await session.commit()
        return {
            "id": str(benchmark.id),
            "status": benchmark.status,
            "summary": benchmark.summary,
        }


async def asyncio_sleep(seconds: int) -> None:
    import asyncio

    await asyncio.sleep(seconds)
