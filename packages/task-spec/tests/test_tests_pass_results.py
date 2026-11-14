from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from agentbench_tasks.schema import Task
from agentbench_tasks.validators.base import (
    InfraError,
    SandboxResult,
    ValidationContext,
)
from agentbench_tasks.validators.tests_pass import (
    JUNIT_PATH,
    PATCH_PATH,
    TestsPassValidator,
)


class _FakeSandbox:
    def __init__(self, result: SandboxResult | None = None) -> None:
        self.result = result or _result()
        self.calls: list[tuple[str, dict[str, bytes], list[str], list[str]]] = []
        self.error: InfraError | None = None

    async def run(
        self,
        image: str,
        files: dict[str, bytes],
        cmd: list[str],
        limits: Any,
        collect_paths: list[str],
    ) -> SandboxResult:
        self.calls.append((image, files, cmd, collect_paths))
        if self.error is not None:
            raise self.error
        return self.result


def _result(
    *,
    exit_code: int | None = 0,
    junit: bytes | None = b"<testsuite><testcase/><testcase/></testsuite>",
    timed_out: bool = False,
    oom_killed: bool = False,
) -> SandboxResult:
    return SandboxResult(
        exit_code=exit_code,
        stdout=b"",
        stderr=b"",
        timed_out=timed_out,
        oom_killed=oom_killed,
        duration_ms=10,
        collected={JUNIT_PATH: junit} if junit is not None else {},
    )


def _task(tmp_path: Path) -> Task:
    task_dir = tmp_path / "sample"
    for folder in ("fixture", "hidden", "reference"):
        (task_dir / folder).mkdir(parents=True, exist_ok=True)
    task_yaml: dict[str, Any] = {
        "id": "sample",
        "category": "coding",
        "version": 1,
        "title": "Sample",
        "prompt": "Implement the feature.",
        "limits": {"timeout_s": 30, "max_steps": 10, "max_cost_usd": 1},
        "validator": {
            "type": "tests_pass",
            "config": {
                "editable_globs": ["src/**"],
                "test_cmd": ["pytest", "-q"],
                "min_tests": 2,
            },
        },
    }
    (task_dir / "task.yaml").write_text(yaml.safe_dump(task_yaml), encoding="utf-8")
    (task_dir / "hidden" / "test_hidden.py").write_text("pass", encoding="utf-8")
    task = Task.model_validate(task_yaml)
    task._task_dir = task_dir
    task._task_yaml = task_yaml
    return task


def _context(task: Task, sandbox: _FakeSandbox, patch: bytes) -> ValidationContext:
    return ValidationContext(
        task=task,
        files={"src/module.py": b"old\n"},
        patch=patch,
        sandbox=sandbox,
    )


def _patch() -> bytes:
    return (
        b"diff --git a/src/module.py b/src/module.py\n"
        b"--- a/src/module.py\n"
        b"+++ b/src/module.py\n"
        b"@@ -1 +1 @@\n"
        b"-old\n"
        b"+new\n"
    )


async def test_zero_collected_tests_never_pass(tmp_path: Path) -> None:
    sandbox = _FakeSandbox(_result(junit=b"<testsuite tests='0'></testsuite>"))
    verdict = await TestsPassValidator().validate(
        _context(_task(tmp_path), sandbox, _patch())
    )
    assert verdict.passed is False
    assert verdict.error_kind == "no_tests"
    assert verdict.score == 0


async def test_empty_patch_runs_tests_and_fails_on_test_failure(tmp_path: Path) -> None:
    junit = (
        b"<testsuite><testcase><failure/></testcase>"
        b"<testcase><failure/></testcase></testsuite>"
    )
    sandbox = _FakeSandbox(_result(exit_code=1, junit=junit))
    verdict = await TestsPassValidator().validate(
        _context(_task(tmp_path), sandbox, b"")
    )
    assert verdict.passed is False
    assert verdict.error_kind == "test_failure"
    assert len(sandbox.calls) == 1
    assert sandbox.calls[0][1][PATCH_PATH] == b""


async def test_timeout_and_oom_map_to_verdicts(tmp_path: Path) -> None:
    task = _task(tmp_path)
    timeout = await TestsPassValidator().validate(
        _context(task, _FakeSandbox(_result(timed_out=True, junit=None)), _patch())
    )
    oom = await TestsPassValidator().validate(
        _context(task, _FakeSandbox(_result(oom_killed=True, junit=None)), _patch())
    )
    assert timeout.error_kind == "timeout"
    assert oom.error_kind == "oom"


async def test_infrastructure_error_is_not_converted_to_verdict(tmp_path: Path) -> None:
    sandbox = _FakeSandbox()
    sandbox.error = InfraError("docker unavailable")
    with pytest.raises(InfraError, match="docker unavailable"):
        await TestsPassValidator().validate(
            _context(_task(tmp_path), sandbox, _patch())
        )


async def test_unapplicable_patch_becomes_patch_invalid(tmp_path: Path) -> None:
    sandbox = _FakeSandbox(_result(exit_code=125, junit=None))
    verdict = await TestsPassValidator().validate(
        _context(_task(tmp_path), sandbox, _patch())
    )
    assert verdict.error_kind == "patch_invalid"
    assert "could not apply" in verdict.details["reason"]


async def test_junit_entity_declaration_is_rejected(tmp_path: Path) -> None:
    junit = (
        b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
        b"<testsuite><testcase>&e;</testcase></testsuite>"
    )
    sandbox = _FakeSandbox(_result(junit=junit))
    verdict = await TestsPassValidator().validate(
        _context(_task(tmp_path), sandbox, _patch())
    )
    assert verdict.passed is False
    assert verdict.error_kind == "test_failure"


async def test_same_patch_produces_identical_verdicts(tmp_path: Path) -> None:
    task = _task(tmp_path)
    first = await TestsPassValidator().validate(
        _context(task, _FakeSandbox(), _patch())
    )
    second = await TestsPassValidator().validate(
        _context(task, _FakeSandbox(), _patch())
    )
    assert first == second
