"""Persist authoritative run usage from LiteLLM spend logs."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentbench_api.config import Settings
from agentbench_api.db import get_session_factory
from agentbench_api.models import Run, Step
from agentbench_api.services.llm_gateway import get_run_usage


async def record_run_usage(
    run_id: UUID,
    *,
    budget_usd: float,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, int | float]:
    """Store LiteLLM usage and make a gateway budget rejection a run failure."""
    factory = session_factory or get_session_factory()
    async with factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0}
        step_rows = cast(
            Sequence[tuple[str, dict[str, Any]]],
            (
                await session.execute(
                    select(Step.type, Step.payload).where(Step.run_id == run_id)
                )
            ).all(),
        )
        has_llm_steps = any(step_type in {"llm", "retry"} for step_type, _ in step_rows)
        budget_was_rejected = any(
            isinstance(payload, dict) and payload.get("budget_exceeded") is True
            for _, payload in step_rows
        )

    usage: dict[str, int | float] = {
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "calls": 0,
    }
    for attempt in range(4):
        usage = await get_run_usage(
            run_id,
            settings=settings,
            session_factory=session_factory,
        )
        if usage["calls"] > 0 or not has_llm_steps or attempt == 3:
            break
        await asyncio.sleep(0.5)

    async with factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return usage
        run.tokens_in = int(usage["tokens_in"])
        run.tokens_out = int(usage["tokens_out"])
        run.cost_usd = Decimal(str(max(0.0, float(usage["cost_usd"]))))
        if budget_was_rejected or float(run.cost_usd) > budget_usd:
            run.status = "agent_error"
            run.verdict = None
            run.failure_cause = "budget_exceeded"
            run.error = "LLM spend exceeded the per-run budget"
        await session.commit()
    return usage
