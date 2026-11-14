"""Leaderboard and comparison endpoints for scored benchmarks."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.deps import get_session
from agentbench_api.models import Benchmark
from agentbench_api.security.auth import require_api_key

router = APIRouter(prefix="/results", tags=["results"])
ApiKey = Annotated[None, Depends(require_api_key)]
Session = Annotated[AsyncSession, Depends(get_session)]


def _etag_response(request: Request, payload: dict[str, object]) -> Response:
    encoded_payload = jsonable_encoder(payload)
    body = json.dumps(
        encoded_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    etag = f'W/"{hashlib.sha256(body).hexdigest()}"'
    if request.headers.get("If-None-Match") == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "private, max-age=60"},
        )
    response = JSONResponse(
        content=encoded_payload,
        headers={"ETag": etag, "Cache-Control": "private, max-age=60"},
    )
    return response


@router.get("/leaderboard")
async def leaderboard(
    request: Request,
    session: Session,
    _: ApiKey,
    category: Annotated[str | None, Query()] = None,
    suite: Annotated[str | None, Query()] = None,
) -> Response:
    statement = (
        select(
            Benchmark.id,
            Benchmark.created_at,
            Benchmark.suite_id,
            Benchmark.summary,
        )
        .where(Benchmark.status == "completed")
        .order_by(Benchmark.created_at.desc())
    )
    benchmarks = (await session.execute(statement)).all()
    latest_by_agent: dict[str, dict[str, object]] = {}
    for benchmark_id, created_at, suite_id, summary in benchmarks:
        benchmark_id = cast(UUID, benchmark_id)
        created_at = cast(datetime, created_at)
        suite_id = cast(str, suite_id)
        if suite is not None and suite_id != suite:
            continue
        summary_dict = cast(dict[str, Any] | None, summary) or {}
        if category is not None and summary_dict.get("category") != category:
            continue
        for agent_id, agent_summary in (summary_dict.get("agents") or {}).items():
            current = latest_by_agent.get(agent_id)
            if current is None or created_at > cast(datetime, current["created_at"]):
                latest_by_agent[agent_id] = {
                    "agent_id": agent_id,
                    "benchmark_id": str(benchmark_id),
                    "created_at": created_at,
                    "success_rate": (agent_summary or {}).get("success_rate", 0.0),
                    "ci": (agent_summary or {}).get("ci", [0.0, 0.0]),
                    "n": (agent_summary or {}).get("n", 0),
                    "summary": agent_summary,
                }
    items = sorted(
        latest_by_agent.values(),
        key=lambda item: (
            -cast(float, item["success_rate"]),
            str(item["agent_id"]),
        ),
    )
    payload: dict[str, object] = {"items": items}
    return _etag_response(request, payload)


@router.get("/compare")
async def compare_benchmarks(
    request: Request,
    session: Session,
    _: ApiKey,
    a: Annotated[UUID, Query(...)],
    b: Annotated[UUID, Query(...)],
    suite: Annotated[str | None, Query()] = None,
) -> Response:
    benchmark_a = await session.get(Benchmark, a)
    benchmark_b = await session.get(Benchmark, b)
    if benchmark_a is None or benchmark_b is None:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    if benchmark_a.suite_id != benchmark_b.suite_id or (
        suite is not None
        and (benchmark_a.suite_id != suite or benchmark_b.suite_id != suite)
    ):
        raise HTTPException(status_code=409, detail="Benchmark suite mismatch")
    digest_a = (benchmark_a.summary or {}).get("task_digests")
    digest_b = (benchmark_b.summary or {}).get("task_digests")
    if not isinstance(digest_a, dict) or not isinstance(digest_b, dict) or not digest_a:
        raise HTTPException(
            status_code=409,
            detail="Benchmark task digests are missing",
        )
    if digest_a != digest_b:
        raise HTTPException(status_code=409, detail="Benchmark task digests differ")
    task_ids = sorted((digest_a or {}).keys())
    task_rows = []
    for task_id in task_ids:
        a_task = (benchmark_a.summary or {}).get("task_passes", {}).get(task_id, {})
        b_task = (benchmark_b.summary or {}).get("task_passes", {}).get(task_id, {})
        a_attempts = int(a_task.get("attempts", 0))
        b_attempts = int(b_task.get("attempts", 0))
        a_passes = int(a_task.get("passes", 0))
        b_passes = int(b_task.get("passes", 0))
        task_rows.append(
            {
                "task_id": task_id,
                "a_passes": a_passes,
                "b_passes": b_passes,
                "delta": b_passes - a_passes,
                "a_success_rate": (a_passes / a_attempts) if a_attempts else 0.0,
                "b_success_rate": (b_passes / b_attempts) if b_attempts else 0.0,
            }
        )
    payload = {
        "a": {
            "id": str(a),
            "status": benchmark_a.status,
            "summary": benchmark_a.summary,
        },
        "b": {
            "id": str(b),
            "status": benchmark_b.status,
            "summary": benchmark_b.summary,
        },
        "deltas": {
            "success_rate": float(
                (benchmark_b.summary or {})
                .get("overall", {})
                .get(
                    "success_rate",
                    0.0,
                )
                - (benchmark_a.summary or {})
                .get("overall", {})
                .get(
                    "success_rate",
                    0.0,
                )
            )
        },
        "task_differences": task_rows,
    }
    return _etag_response(request, payload)
