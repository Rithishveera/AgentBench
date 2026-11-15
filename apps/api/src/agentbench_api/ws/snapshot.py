"""Build the full benchmark snapshot for the initial WS message and resyncs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.models import Benchmark, Run


async def build_snapshot(
    session: AsyncSession, benchmark_id: UUID
) -> dict[str, Any] | None:
    """Return benchmark + all run rows as a snapshot dict, or None if not found."""
    benchmark = await session.get(Benchmark, benchmark_id)
    if benchmark is None:
        return None

    rows = list(
        (
            await session.execute(
                select(
                    Run.id,
                    Run.agent_id,
                    Run.task_id,
                    Run.attempt_no,
                    Run.fault_mode,
                    Run.status,
                    Run.verdict,
                    Run.cost_usd,
                    Run.duration_ms,
                    Run.started_at,
                    Run.finished_at,
                ).where(Run.benchmark_id == benchmark_id)
            )
        ).all()
    )

    return {
        "type": "snapshot",
        "benchmark": {
            "id": str(benchmark.id),
            "status": benchmark.status,
            "summary": benchmark.summary,
            "created_at": (
                benchmark.created_at.isoformat() if benchmark.created_at else None
            ),
            "finished_at": (
                benchmark.finished_at.isoformat() if benchmark.finished_at else None
            ),
        },
        "runs": [
            {
                "id": str(r[0]),
                "agent_id": str(r[1]),
                "task_id": r[2],
                "attempt_no": r[3],
                "fault_mode": r[4],
                "status": r[5],
                "passed": r[6].get("passed") if r[6] else None,
                "cost_usd": float(r[7]) if isinstance(r[7], Decimal) else r[7],
                "duration_ms": r[8],
                "started_at": r[9].isoformat() if r[9] else None,
                "finished_at": r[10].isoformat() if r[10] else None,
            }
            for r in rows
        ],
    }
