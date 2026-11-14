from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from agentbench_api.models import Benchmark
from agentbench_api.routers.results import compare_benchmarks, leaderboard
from fastapi import HTTPException, Request


class FakeResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self.rows


class FakeSession:
    def __init__(
        self,
        *,
        rows: list[tuple[object, ...]] | None = None,
        benchmarks: list[Benchmark] | None = None,
    ) -> None:
        self.rows = rows or []
        self.benchmarks = {benchmark.id: benchmark for benchmark in benchmarks or []}
        self.query_count = 0

    async def execute(self, _statement: object) -> FakeResult:
        self.query_count += 1
        return FakeResult(self.rows)

    async def get(self, _model: type[Benchmark], key: object) -> Benchmark | None:
        return self.benchmarks.get(key)


def _request() -> Request:
    return Request({"type": "http", "headers": []})


@pytest.mark.asyncio
async def test_leaderboard_uses_one_query_and_selects_latest_agent_result() -> None:
    now = datetime.now(UTC)
    agent_id = str(uuid4())
    session = FakeSession(
        rows=[
            (
                uuid4(),
                now,
                "coding",
                {
                    "category": "coding",
                    "agents": {agent_id: {"success_rate": 0.8, "n": 10}},
                },
            ),
            (
                uuid4(),
                now - timedelta(days=1),
                "coding",
                {
                    "category": "coding",
                    "agents": {agent_id: {"success_rate": 0.4, "n": 10}},
                },
            ),
            (
                uuid4(),
                now + timedelta(days=1),
                "coding",
                {"agents": {str(uuid4()): {"success_rate": 1.0, "n": 1}}},
            ),
        ]
    )

    response = await leaderboard(_request(), session, None, category="coding")

    payload = json.loads(response.body)
    assert session.query_count == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["agent_id"] == agent_id
    assert payload["items"][0]["success_rate"] == 0.8


@pytest.mark.asyncio
async def test_compare_rejects_different_task_digests() -> None:
    benchmark_a = Benchmark(
        id=uuid4(),
        suite_id="coding",
        status="completed",
        summary={"task_digests": {"task-a": "a"}},
    )
    benchmark_b = Benchmark(
        id=uuid4(),
        suite_id="coding",
        status="completed",
        summary={"task_digests": {"task-a": "b"}},
    )
    session = FakeSession(benchmarks=[benchmark_a, benchmark_b])

    with pytest.raises(HTTPException) as error:
        await compare_benchmarks(
            _request(),
            session,
            None,
            benchmark_a.id,
            benchmark_b.id,
        )

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_compare_rejects_missing_task_digests() -> None:
    benchmark_a = Benchmark(
        id=uuid4(),
        suite_id="coding",
        status="completed",
        summary={},
    )
    benchmark_b = Benchmark(
        id=uuid4(),
        suite_id="coding",
        status="completed",
        summary={},
    )
    session = FakeSession(benchmarks=[benchmark_a, benchmark_b])

    with pytest.raises(HTTPException) as error:
        await compare_benchmarks(
            _request(),
            session,
            None,
            benchmark_a.id,
            benchmark_b.id,
        )

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_compare_reports_deltas_when_task_digests_match() -> None:
    benchmark_a = Benchmark(
        id=uuid4(),
        suite_id="coding",
        status="completed",
        summary={
            "overall": {"success_rate": 0.4},
            "task_digests": {"task-a": "digest"},
            "task_passes": {"task-a": {"attempts": 2, "passes": 1}},
        },
    )
    benchmark_b = Benchmark(
        id=uuid4(),
        suite_id="coding",
        status="completed",
        summary={
            "overall": {"success_rate": 0.6},
            "task_digests": {"task-a": "digest"},
            "task_passes": {"task-a": {"attempts": 2, "passes": 2}},
        },
    )
    session = FakeSession(benchmarks=[benchmark_a, benchmark_b])

    response = await compare_benchmarks(
        _request(),
        session,
        None,
        benchmark_a.id,
        benchmark_b.id,
    )

    payload = json.loads(response.body)
    assert response.status_code == 200
    assert payload["deltas"]["success_rate"] == pytest.approx(0.2)
    assert payload["task_differences"][0]["delta"] == 1
