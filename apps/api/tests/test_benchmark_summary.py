from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from agentbench_api.services.benchmark_summary import finalize_benchmark


class _Result:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return self.rows


class _Session:
    def __init__(self, benchmark: SimpleNamespace, rows: list[tuple[Any, ...]]) -> None:
        self.benchmark = benchmark
        self.rows = rows

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, _model: object, _key: object) -> SimpleNamespace:
        return self.benchmark

    async def execute(self, _statement: object) -> _Result:
        return _Result(self.rows)

    async def commit(self) -> None:
        return None


class _Factory:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def __call__(self) -> _Session:
        return self.session


@pytest.mark.asyncio
async def test_paired_summary_uses_baseline_attempts_for_pass_k() -> None:
    benchmark_id = uuid4()
    agent_id = uuid4()
    benchmark = SimpleNamespace(
        id=benchmark_id,
        paired=True,
        repetitions=3,
        status="running",
        finished_at=None,
        summary=None,
    )
    modes = [("none", True)] * 3 + [("faulted", False)] * 3
    rows = [
        (
            agent_id,
            "task-a",
            "a" * 64,
            mode,
            "completed",
            {"passed": passed},
            None,
            1,
            0,
            1000,
            Decimal("0.01"),
        )
        for mode, passed in modes
    ]
    factory = _Factory(_Session(benchmark, rows))

    result = await finalize_benchmark(benchmark_id, session_factory=factory)  # type: ignore[arg-type]

    agent_summary = result["summary"]["agents"][str(agent_id)]
    assert agent_summary["pass_at_k"] == {
        "k": 3,
        "value": 1.0,
        "excluded": 0,
        "n": 1,
    }
    assert agent_summary["resilience"] == 0.0
    assert result["status"] == "completed"
