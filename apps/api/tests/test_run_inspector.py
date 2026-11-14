from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agentbench_api.models import Run
from agentbench_api.routers.runs import get_run_faults, get_run_step, get_run_steps
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder


class _Rows:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self.rows


class _Session:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.statement: object | None = None
        self.step = SimpleNamespace(
            seq=4,
            type="tool",
            started_at=datetime.now(UTC),
            duration_ms=25,
            ok=False,
            payload={"name": "inspect", "result": "<script>alert(1)</script>"},
            truncated=False,
        )

    async def get(self, model: object, key: object) -> object | None:
        if model is Run:
            return object()
        return self.step if key == (self.step.run_id, self.step.seq) else self.step

    async def execute(self, statement: object) -> _Rows:
        self.statement = statement
        return _Rows(self.rows)


@pytest.mark.asyncio
async def test_step_summary_is_paginated_and_never_returns_payload() -> None:
    first_ts = datetime.now(UTC)
    session = _Session(
        [
            (
                0,
                "llm",
                first_ts,
                120,
                True,
                "model-a",
                False,
            ),
            (1, "tool", first_ts, 25, False, {"name": "lint", "result": "bad"}, True),
        ]
    )

    result = await get_run_steps(uuid4(), session, None, limit=1)  # type: ignore[arg-type]

    item = result["items"][0]  # type: ignore[index]
    assert item["short_label"] == "model-a"
    assert item["ts"] == first_ts
    assert "payload" not in item
    assert all(
        getattr(column, "name", None) != "payload"
        for column in session.statement.selected_columns  # type: ignore[union-attr]
    )
    assert result["next_cursor"] == 0


@pytest.mark.asyncio
async def test_thousand_step_summary_page_stays_payload_free_and_small() -> None:
    now = datetime.now(UTC)
    rows = [(seq, "llm", now, 10, True, "model", False) for seq in range(1000)]
    result = await get_run_steps(uuid4(), _Session(rows), None, limit=100)  # type: ignore[arg-type]
    body = json.dumps(jsonable_encoder(result)).encode()

    assert len(result["items"]) == 100  # type: ignore[arg-type]
    assert result["next_cursor"] == 99
    assert b"x" * 256 not in body
    assert len(body) < 40_000


@pytest.mark.asyncio
async def test_step_detail_returns_raw_payload_for_text_rendering() -> None:
    session = _Session([])
    session.step.run_id = uuid4()

    result = await get_run_step(session.step.run_id, 4, session, None)  # type: ignore[arg-type]

    assert result["payload"]["result"] == "<script>alert(1)</script>"  # type: ignore[index]


@pytest.mark.asyncio
async def test_fault_events_are_keyset_paginated_with_reactions() -> None:
    now = datetime.now(UTC)
    session = _Session(
        [
            (0, "rate_limit_429", now, "retried_ok", {"count": 2}),
            (1, "rate_limit_429", now, "retried_ok", {"count": 2}),
        ]
    )

    result = await get_run_faults(uuid4(), session, None, limit=1)  # type: ignore[arg-type]

    assert result["items"][0]["agent_reaction"] == "retried_ok"  # type: ignore[index]
    assert result["next_cursor"] == 0


@pytest.mark.asyncio
async def test_step_detail_returns_not_found_for_unknown_run() -> None:
    session = _Session([])
    session.get = _missing_run  # type: ignore[method-assign]

    with pytest.raises(HTTPException) as error:
        await get_run_step(uuid4(), 0, session, None)  # type: ignore[arg-type]

    assert error.value.status_code == 404


async def _missing_run(_model: object, _key: object) -> None:
    return None
