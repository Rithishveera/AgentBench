from __future__ import annotations

from typing import Any

import pytest
from agentbench_sdk.context import RunContext
from agentbench_sdk.schemas import RunTask, StepType


class _Recorder:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def push(
        self,
        event_type: StepType,
        payload: dict[str, Any],
        *,
        ok: bool,
        started_at: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        self.events.append(
            {
                "type": event_type,
                "payload": payload,
                "ok": ok,
                "started_at": started_at,
                "duration_ms": duration_ms,
            }
        )


def _context() -> tuple[RunContext, _Recorder]:
    task = RunTask.model_validate(
        {
            "id": "task-one",
            "category": "coding",
            "prompt": "Implement a change.",
            "files": [],
            "limits": {"timeout_s": 30, "max_steps": 10, "max_cost_usd": 1.0},
        }
    )
    recorder = _Recorder()
    return (
        RunContext(
            task,
            None,
            recorder,  # type: ignore[arg-type]
        ),
        recorder,
    )


async def test_tool_context_records_success() -> None:
    context, recorder = _context()
    async with context.tool("read_file"):
        pass
    assert recorder.events[0]["type"] == "tool"
    assert recorder.events[0]["payload"] == {"name": "read_file"}
    assert recorder.events[0]["ok"] is True
    assert recorder.events[0]["duration_ms"] >= 0


async def test_step_records_given_type_and_payload() -> None:
    context, recorder = _context()
    await context.step("llm", {"model": "test-model"}, ok=False)
    assert recorder.events == [
        {
            "type": "llm",
            "payload": {"model": "test-model"},
            "ok": False,
            "started_at": None,
            "duration_ms": 0,
        }
    ]


async def test_tool_context_records_exception_and_reraises() -> None:
    context, recorder = _context()
    with pytest.raises(RuntimeError, match="tool failed"):
        async with context.tool("write_file"):
            raise RuntimeError("tool failed")
    assert recorder.events[0]["ok"] is False
    assert recorder.events[0]["payload"] == {
        "name": "write_file",
        "error_type": "RuntimeError",
    }


async def test_context_closes_without_opening_llm_client() -> None:
    context, _ = _context()
    await context.close()
