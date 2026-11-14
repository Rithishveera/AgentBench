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
    junit: bytes | None = b"""<testsuite><testcase/><testcase/></testsuite>""",
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


def _patch(
    path: str = "src/module.py",
    *,
    source: str = "a/src/module.py",
    target: str = "b/src/module.py",
    info: str = "",
) -> bytes:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"{info}"
        f"--- {source}\n"
        f"+++ {target}\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    ).encode()


def _delete_patch(path: str) -> bytes:
    return (
        f"diff --git a/{path} b/{path}\n"
        "deleted file mode 100644\n"
        "index 1111111..0000000\n"
        f"--- a/{path}\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-old\n"
    ).encode()


def _symlink_patch(path: str) -> bytes:
    return (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 120000\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        "@@ -0,0 +1 @@\n"
        "+target\n"
    ).encode()


def _rename_patch() -> bytes:
    return (
        b"diff --git a/src/module.py b/tests/evil.py\n"
        b"similarity index 100%\n"
        b"rename from src/module.py\n"
        b"rename to tests/evil.py\n"
        b"--- a/src/module.py\n"
        b"+++ b/tests/evil.py\n"
        b"@@ -1 +1 @@\n"
        b"-old\n"
        b"+new\n"
    )


def _binary_patch() -> bytes:
    return (
        b"diff --git a/src/module.py b/src/module.py\n"
        b"index 1111111..2222222 100644\n"
        b"Binary files a/src/module.py and b/src/module.py differ\n"
    )


def _task(tmp_path: Path, *, config: dict[str, Any] | None = None) -> Task:
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
            "config": config
            or {
                "editable_globs": ["src/**"],
                "test_cmd": ["pytest", "-q"],
                "min_tests": 2,
            },
        },
    }
    (task_dir / "task.yaml").write_text(yaml.safe_dump(task_yaml), encoding="utf-8")
    (task_dir / "fixture" / "src").mkdir()
    (task_dir / "fixture" / "src" / "module.py").write_text("old\n", encoding="utf-8")
    (task_dir / "hidden" / "tests").mkdir()
    (task_dir / "hidden" / "tests" / "test_hidden.py").write_bytes(b"hidden tests")
    task = Task.model_validate(task_yaml)
    task._task_dir = task_dir
    task._task_yaml = task_yaml
    return task


def _context(
    task: Task,
    sandbox: _FakeSandbox,
    patch: bytes,
    files: dict[str, bytes] | None = None,
) -> ValidationContext:
    return ValidationContext(
        task=task,
        files=files or {"src/module.py": b"old\n"},
        patch=patch,
        sandbox=sandbox,
    )


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        (
            _patch(
                "tests/test_hidden.py",
                source="a/tests/test_hidden.py",
                target="b/tests/test_hidden.py",
            ),
            "not allowed",
        ),
        (
            _patch("conftest.py", source="a/conftest.py", target="b/conftest.py"),
            "not allowed",
        ),
        (_delete_patch("tests/test_public.py"), "not allowed"),
        (_rename_patch(), "not allowed"),
        (_symlink_patch("src/link"), "symlink mode"),
        (_binary_patch(), "binary patch"),
        (
            _patch(
                "src/../../etc/passwd",
                source="a/src/../../etc/passwd",
                target="b/src/../../etc/passwd",
            ),
            "escapes",
        ),
        (b"\xff\x00", "UTF-8"),
        (b"x" * (256 * 1024 + 1), "256 KB"),
        (b"not a diff", "no unified diff"),
    ],
)
async def test_invalid_patches_never_run_in_sandbox(
    tmp_path: Path, patch: bytes, reason: str
) -> None:
    sandbox = _FakeSandbox()
    verdict = await TestsPassValidator().validate(
        _context(_task(tmp_path), sandbox, patch)
    )
    assert verdict.passed is False
    assert verdict.error_kind == "patch_invalid"
    assert reason in verdict.details["reason"]
    assert sandbox.calls == []


async def test_hidden_files_override_fixture_and_only_one_sandbox_run(
    tmp_path: Path,
) -> None:
    sandbox = _FakeSandbox()
    task = _task(tmp_path)
    context = _context(
        task,
        sandbox,
        _patch(),
        {"src/module.py": b"old\n", "tests/test_hidden.py": b"visible fake"},
    )
    verdict = await TestsPassValidator().validate(context)
    assert verdict.passed is True
    assert verdict.score == 1
    assert len(sandbox.calls) == 1
    _, files, command, collect_paths = sandbox.calls[0]
    assert files["tests/test_hidden.py"] == b"hidden tests"
    assert files[PATCH_PATH] == _patch()
    assert '"git", "apply"' in command[2]
    assert collect_paths == [JUNIT_PATH]
