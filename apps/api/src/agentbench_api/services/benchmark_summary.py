"""Persist aggregate benchmark metrics after its runs reach terminal states."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentbench_api.db import get_session_factory
from agentbench_api.models import Benchmark, Run
from agentbench_api.services.scorer import pass_at_k, summarize_runs


async def finalize_benchmark(
    benchmark_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, Any]:
    """Store overall, per-agent, and task-level aggregates on a benchmark."""
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
                    str,
                    dict[str, Any] | None,
                    str | None,
                    int,
                    int,
                    int | None,
                    Decimal,
                ]
            ],
            (
                await session.execute(
                    select(
                        Run.agent_id,
                        Run.task_id,
                        Run.task_digest,
                        Run.fault_mode,
                        Run.status,
                        Run.verdict,
                        Run.failure_cause,
                        Run.steps_count,
                        Run.tool_calls,
                        Run.duration_ms,
                        Run.cost_usd,
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
        agent_mode_task_passes: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
        mode_task_passes: dict[str, dict[str, dict[str, int]]] = {}
        run_rows: list[dict[str, Any]] = []
        for (
            run_agent_id,
            task_id,
            task_digest,
            fault_mode,
            status,
            verdict,
            failure_cause,
            steps_count,
            tool_calls,
            duration_ms,
            cost_usd,
        ) in rows:
            passed = bool(verdict and verdict.get("passed") is True)
            status_breakdown[status] = status_breakdown.get(status, 0) + 1
            run_data = {
                "fault_mode": fault_mode,
                "status": status,
                "passed": passed,
                "failure_cause": failure_cause,
                "steps_count": steps_count,
                "tool_calls": tool_calls,
                "duration_ms": duration_ms,
                "cost_usd": float(cost_usd),
            }
            run_rows.append(run_data)
            task_digests[task_id] = task_digest
            task_entry = task_passes.setdefault(task_id, {"attempts": 0, "passes": 0})
            agent_task_entry = agent_task_passes.setdefault(
                str(run_agent_id), {}
            ).setdefault(task_id, {"attempts": 0, "passes": 0})
            agent_mode_entry = (
                agent_mode_task_passes.setdefault(str(run_agent_id), {})
                .setdefault(fault_mode, {})
                .setdefault(task_id, {"attempts": 0, "passes": 0})
            )
            mode_entry = mode_task_passes.setdefault(fault_mode, {}).setdefault(
                task_id,
                {"attempts": 0, "passes": 0},
            )
            if status in {"completed", "agent_error", "timeout"}:
                task_entry["attempts"] += 1
                agent_task_entry["attempts"] += 1
                agent_mode_entry["attempts"] += 1
                mode_entry["attempts"] += 1
                if status == "completed" and passed:
                    task_entry["passes"] += 1
                    agent_task_entry["passes"] += 1
                    agent_mode_entry["passes"] += 1
                    mode_entry["passes"] += 1
            agent_runs.setdefault(str(run_agent_id), []).append(run_data)

        agent_summaries: dict[str, dict[str, Any]] = {}
        for agent_id, agent_run_rows in agent_runs.items():
            summary = summarize_runs(agent_run_rows)
            summary["agent_id"] = agent_id
            summary["task_passes"] = {
                task_id: agent_task_passes[agent_id].get(
                    task_id,
                    {"attempts": 0, "passes": 0},
                )
                for task_id in sorted(task_passes)
            }
            pass_mode = "none" if benchmark.paired else "faulted"
            if pass_mode not in agent_mode_task_passes[agent_id]:
                pass_mode = "none"
            k = min(3, benchmark.repetitions)
            summary["pass_at_k"] = {
                "k": k,
                **pass_at_k(
                    [
                        (values["attempts"], values["passes"])
                        for values in agent_mode_task_passes[agent_id]
                        .get(pass_mode, {})
                        .values()
                    ],
                    k,
                ),
            }
            agent_summaries[agent_id] = summary

        overall = summarize_runs(run_rows)
        pass_mode = "none" if benchmark.paired else "faulted"
        if pass_mode not in mode_task_passes:
            pass_mode = "none"
        k = min(3, benchmark.repetitions)
        overall["pass_at_k"] = {
            "k": k,
            **pass_at_k(
                [
                    (values["attempts"], values["passes"])
                    for values in mode_task_passes.get(pass_mode, {}).values()
                ],
                k,
            ),
        }
        overall["task_passes"] = {
            task_id: task_values for task_id, task_values in sorted(task_passes.items())
        }
        benchmark.summary = {
            "status_breakdown": status_breakdown,
            "overall": overall,
            "agents": agent_summaries,
            "task_passes": overall["task_passes"],
            "task_digests": task_digests,
            "category": "coding",
        }
        if rows and all(
            status in {"completed", "agent_error", "timeout", "infra_error"}
            for _, _, _, _, status, *_ in rows
        ):
            benchmark.status = "completed"
            benchmark.finished_at = datetime.now(UTC)
        elif rows and any(
            status in {"running", "queued"} for _, _, _, _, status, *_ in rows
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
