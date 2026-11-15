"""Run execution and terminalization service."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from agentbench_sdk.client import AgentClient
from agentbench_sdk.schemas import (
    CallbackConfig,
    LLMConfig,
)
from agentbench_tasks.loader import Suite
from agentbench_tasks.validators.base import InfraError
from pydantic import AnyHttpUrl
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentbench_api.config import Settings
from agentbench_api.crypto import decrypt_agent_secret
from agentbench_api.db import get_session_factory
from agentbench_api.models import Agent, Run, TaskRecord
from agentbench_api.repositories import claim_run, mark_run_terminal
from agentbench_api.services.agent_request import _run_request_for, _task_model
from agentbench_api.services.llm_gateway import managed_run_key
from agentbench_api.services.metrics import record_run_usage
from agentbench_api.services.sandbox import DockerSandbox
from agentbench_api.services.validator import validate_run
from agentbench_api.ws.hub import publish as hub_publish

logger = structlog.get_logger(__name__)


async def _publish_run_status(
    redis_client: Any,
    run: Run,
    status: str,
    *,
    passed: bool | None = None,
    cost_usd: float | None = None,
) -> None:
    """Fire-and-forget publish of a run status event to the benchmark channel."""
    if redis_client is None:
        return
    try:
        event: dict[str, Any] = {
            "type": "run_update",
            "run_id": str(run.id),
            "agent_id": str(run.agent_id),
            "task_id": run.task_id,
            "status": status,
        }
        if passed is not None:
            event["passed"] = passed
        if cost_usd is not None:
            event["cost_usd"] = cost_usd
        await hub_publish(redis_client, run.benchmark_id, event)
    except Exception:
        logger.warning("run_status_publish_failed", run_id=str(run.id))


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
            await _publish_run_status(redis_client, run, "running")
        if run.status not in {"queued", "running"}:
            return True

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
            await _publish_run_status(redis_client, run, "infra_error")
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
            await _publish_run_status(redis_client, run, "infra_error")
            return False

        task = await _task_model(task_record)
        _, request = await _run_request_for(session, run, suites=suites)
        token = secrets.token_urlsafe(32)
        run.token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        timeout_seconds = max(1, int(task.limits.timeout_s))
        run.token_expires_at = datetime.now(UTC) + timedelta(
            seconds=timeout_seconds + 60
        )
        request.callback = CallbackConfig(
            base_url=AnyHttpUrl(settings.agent_callback_base_url),
            token=token,
        )
        secret = decrypt_agent_secret(agent.secret_encrypted, settings.encryption_key)
        try:
            async with managed_run_key(
                run.id,
                [settings.litellm_model],
                max_budget_usd=task.limits.max_cost_usd,
                ttl=timeout_seconds + 60,
                settings=settings,
            ) as llm_key:
                run.litellm_key_hash = hashlib.sha256(
                    llm_key.encode("utf-8")
                ).hexdigest()
                request.llm = LLMConfig(
                    base_url=AnyHttpUrl(settings.litellm_url.rstrip("/") + "/v1"),
                    api_key=llm_key,
                    model=settings.litellm_model,
                )
                await session.commit()
                try:
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
                        await _publish_run_status(redis_client, run, "infra_error")
                        return False
                    finally:
                        await client.close()

                    await session.commit()
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
                            await _publish_run_status(redis_client, run, "timeout")
                            return True

                    refreshed = await session.get(Run, run.id)
                    if refreshed is None:
                        return False
                    if refreshed.status in {"agent_error", "timeout", "infra_error"}:
                        await _publish_run_status(redis_client, run, refreshed.status)
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
                        await _publish_run_status(redis_client, run, "timeout")
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
                        await _publish_run_status(redis_client, run, "infra_error")
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
                        await _publish_run_status(redis_client, run, "infra_error")
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
                    await _publish_run_status(
                        redis_client,
                        run,
                        "completed",
                        passed=verdict.passed,
                        cost_usd=float(refreshed.cost_usd or 0),
                    )
                    return True
                finally:
                    try:
                        await record_run_usage(
                            run.id,
                            budget_usd=task.limits.max_cost_usd,
                            settings=settings,
                            session_factory=session_factory,
                        )
                    except Exception as exc:
                        logger.error(
                            "run_usage_reconciliation_failed",
                            run_id=str(run.id),
                            error_type=type(exc).__name__,
                        )
        except Exception as exc:
            await session.refresh(run)
            if run.status in {"queued", "running"}:
                await mark_run_terminal(
                    session,
                    run.id,
                    "infra_error",
                    failure_cause="llm_gateway",
                    error=f"gateway or run execution failed: {type(exc).__name__}",
                )
                await session.commit()
                await _publish_run_status(redis_client, run, "infra_error")
                return False
            logger.error(
                "run_key_revocation_failed",
                run_id=str(run.id),
                error_type=type(exc).__name__,
            )
            return True


async def finalize_benchmark(
    benchmark_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, Any]:
    """Compatibility entry point for benchmark summary finalization."""
    from agentbench_api.services.benchmark_summary import (
        finalize_benchmark as finalize_summary,
    )

    return await finalize_summary(benchmark_id, session_factory=session_factory)


async def asyncio_sleep(seconds: int) -> None:
    import asyncio

    await asyncio.sleep(seconds)
