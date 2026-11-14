from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agentbench_api.routers.benchmarks import list_benchmark_runs
from fastapi import HTTPException


class _Rows:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self.rows


class _Session:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.benchmark_exists = True

    async def get(self, model: object, key: object) -> object | None:
        del model, key
        return SimpleNamespace(id=uuid4()) if self.benchmark_exists else None

    async def execute(self, statement: object) -> _Rows:
        del statement
        return _Rows(self.rows)


def _run_row(run_id: object) -> tuple[object, ...]:
    return (
        run_id,
        uuid4(),
        "task-one",
        1,
        "faulted",
        "completed",
        {"passed": True},
        None,
        1200,
        Decimal("0.04"),
        None,
        None,
    )


@pytest.mark.asyncio
async def test_list_benchmark_runs_paginates_without_artifacts() -> None:
    first_id = uuid4()
    session = _Session([_run_row(first_id), _run_row(uuid4())])

    page = await list_benchmark_runs(uuid4(), None, session, limit=1)  # type: ignore[arg-type]

    assert len(page["items"]) == 1  # type: ignore[arg-type]
    assert page["next_cursor"] == str(first_id)
    assert "artifact" not in page["items"][0]  # type: ignore[index]


@pytest.mark.asyncio
async def test_list_benchmark_runs_rejects_unknown_benchmark() -> None:
    session = _Session([])
    session.benchmark_exists = False

    with pytest.raises(HTTPException) as error:
        await list_benchmark_runs(uuid4(), None, session, limit=10)  # type: ignore[arg-type]

    assert error.value.status_code == 404
