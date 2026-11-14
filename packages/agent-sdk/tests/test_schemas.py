from __future__ import annotations

import json

import pytest
from agentbench_sdk.schemas import (
    MAX_PATCH_BYTES,
    MAX_STEP_PAYLOAD_BYTES,
    CompleteRequest,
    RunRequest,
    RunResult,
    StepEvent,
)
from pydantic import ValidationError


def _request(files: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "run_id": "run-1",
        "task": {
            "id": "task-one",
            "category": "coding",
            "prompt": "Implement the change.",
            "files": files or [{"path": "src/main.py", "content": "pass\n"}],
            "limits": {"timeout_s": 30, "max_steps": 20, "max_cost_usd": 1.0},
        },
        "llm": {
            "base_url": "https://llm.example/v1",
            "api_key": "test-key",
            "model": "test-model",
        },
        "callback": {
            "base_url": "https://platform.example/callback",
            "token": "t" * 32,
        },
    }


def test_run_request_accepts_shared_context_contract() -> None:
    request = RunRequest.model_validate(_request())
    assert request.run_id == "run-1"
    assert request.task.files[0].path == "src/main.py"
    assert request.llm is not None
    assert request.llm.api_key == "test-key"


def test_run_request_forbids_unknown_nested_fields() -> None:
    value = _request()
    value["task"]["hidden"] = "not allowed"  # type: ignore[index]
    with pytest.raises(ValidationError):
        RunRequest.model_validate(value)


def test_run_request_caps_total_utf8_file_bytes() -> None:
    value = _request(
        [
            {"path": "a.txt", "content": "a" * 600_000},
            {"path": "b.txt", "content": "b" * 450_000},
        ]
    )
    with pytest.raises(ValidationError, match="1 MB total"):
        RunRequest.model_validate(value)


def test_run_request_rejects_nul_in_text_file() -> None:
    value = _request([{"path": "file", "content": "a\x00b"}])
    with pytest.raises(ValidationError, match="text"):
        RunRequest.model_validate(value)


def test_step_payload_is_truncated_with_flag() -> None:
    event = StepEvent(
        seq=0,
        type="tool",
        started_at="2026-11-14T00:00:00Z",
        duration_ms=1,
        ok=True,
        payload={"data": "x" * (MAX_STEP_PAYLOAD_BYTES + 100)},
    )
    assert event.truncated is True
    assert len(json.dumps(event.payload).encode()) < MAX_STEP_PAYLOAD_BYTES
    assert len(event.model_dump_json().encode()) <= MAX_STEP_PAYLOAD_BYTES


def test_step_payload_truncation_handles_control_characters() -> None:
    event = StepEvent(
        seq=0,
        type="tool",
        started_at="2026-11-14T00:00:00Z",
        duration_ms=1,
        ok=True,
        payload={"data": "\u0001" * (MAX_STEP_PAYLOAD_BYTES + 100)},
    )
    assert event.truncated is True
    assert len(event.model_dump_json().encode()) <= MAX_STEP_PAYLOAD_BYTES


def test_run_result_caps_patch_by_utf8_bytes() -> None:
    with pytest.raises(ValidationError, match="256 KB"):
        RunResult(patch="x" * (MAX_PATCH_BYTES + 1))


def test_complete_request_requires_error_for_failed_status() -> None:
    with pytest.raises(ValidationError, match="requires an error"):
        CompleteRequest(status="error")


def test_complete_request_accepts_error_completion_and_drop_count() -> None:
    complete = CompleteRequest(status="error", error="handler failed", steps_dropped=2)
    assert complete.steps_dropped == 2
