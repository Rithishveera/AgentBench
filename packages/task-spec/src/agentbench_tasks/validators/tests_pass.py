"""Validate unified patches by running a task's pytest suite in a sandbox."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from agentbench_tasks.validators.base import (
    InfraError,
    SandboxResult,
    ValidationContext,
    Verdict,
)
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring
from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

MAX_PATCH_BYTES = 256 * 1024
MAX_TEST_FILES = 500
MAX_HIDDEN_BYTES = 14 * 1024 * 1024
PATCH_PATH = ".agentbench-internal/solution.patch"
JUNIT_PATH = ".agentbench-internal/junit.xml"
SANDBOX_IMAGE = "agentbench/sandbox:py312"

_WRAPPER = """
import json
import os
import subprocess
import sys

patch_path, junit_path, command_json = sys.argv[1:4]
test_command = json.loads(command_json)
os.makedirs(os.path.dirname(junit_path), exist_ok=True)
if os.path.getsize(patch_path):
    result = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", patch_path],
        cwd="/workspace",
        check=False,
    )
    if result.returncode:
        raise SystemExit(125)
if test_command[0] in {"pytest", "py.test"}:
    test_command.append("--junitxml=" + junit_path)
elif (
    len(test_command) > 2
    and test_command[0] in {"python", "python3"}
    and test_command[1:3] == ["-m", "pytest"]
):
    test_command.append("--junitxml=" + junit_path)
raise SystemExit(subprocess.run(test_command, cwd="/workspace", check=False).returncode)
"""


def _invalid_patch(reason: str) -> Verdict:
    return Verdict(
        passed=False,
        score=0,
        error_kind="patch_invalid",
        details={"reason": reason},
    )


def _normalize_patch_path(raw_path: str, prefix: str) -> str | None:
    if raw_path == "/dev/null":
        return None
    path = raw_path.removeprefix(prefix)
    normalized = PurePosixPath(path)
    if (
        not path
        or "\\" in path
        or "\x00" in path
        or normalized.is_absolute()
        or PureWindowsPath(path).drive
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError(f"path escapes the task workspace: {raw_path!r}")
    return path


def _validate_patch(artifact: bytes, editable_globs: list[str]) -> str | None:
    if len(artifact) > MAX_PATCH_BYTES:
        return "patch exceeds 256 KB"
    try:
        patch_text = artifact.decode("utf-8")
    except UnicodeDecodeError:
        return "patch is not UTF-8 text"
    if "\x00" in patch_text:
        return "patch contains binary data"
    try:
        patch_set = PatchSet(patch_text.splitlines(keepends=True))
    except (UnidiffParseError, ValueError) as error:
        return f"patch is not a valid unified diff: {error}"
    if patch_text.strip() and not patch_set:
        return "patch contains no unified diff files"

    for patched_file in patch_set:
        if patched_file.is_binary_file:
            return f"binary patch is not allowed: {patched_file.path}"
        for info in patched_file.patch_info or []:
            line = str(info).strip()
            if re.fullmatch(r"(?:old mode|new mode|new file mode) 120000", line) or (
                line.startswith("index ") and line.endswith(" 120000")
            ):
                return f"symlink mode 120000 is not allowed: {patched_file.path}"
        try:
            source = _normalize_patch_path(patched_file.source_file, "a/")
            target = _normalize_patch_path(patched_file.target_file, "b/")
        except ValueError as error:
            return str(error)
        for path in (source, target):
            if path is not None and not any(
                fnmatch.fnmatchcase(path, pattern) for pattern in editable_globs
            ):
                return f"path is not allowed by editable_globs: {path}"
    return None


def _hidden_files(context: ValidationContext) -> dict[str, bytes]:
    task_dir = context.task._task_dir
    if task_dir is None:
        raise InfraError("task must be loaded from a suite before validation")
    hidden_root = task_dir / "hidden"
    if not hidden_root.is_dir() or hidden_root.is_symlink():
        raise InfraError("task hidden directory is missing or unsafe")

    files: dict[str, bytes] = {}
    total_bytes = 0
    for current, directories, names in os.walk(hidden_root, followlinks=False):
        directories.sort()
        names.sort()
        current_path = Path(current)
        for name in [*directories, *names]:
            if (current_path / name).is_symlink():
                raise InfraError("task hidden files must not contain symlinks")
        for name in names:
            path = current_path / name
            if not stat.S_ISREG(path.stat().st_mode):
                raise InfraError("task hidden entries must be regular files")
            relative = path.relative_to(hidden_root).as_posix()
            if len(files) >= MAX_TEST_FILES:
                raise InfraError("hidden test tree exceeds 500 files")
            total_bytes += path.stat().st_size
            if total_bytes > MAX_HIDDEN_BYTES:
                raise InfraError("hidden test tree exceeds its size limit")
            files[relative] = path.read_bytes()
    return files


def _test_command(config: dict[str, Any]) -> tuple[list[str], int]:
    command = config.get("test_cmd")
    min_tests = config.get("min_tests", 1)
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(argument, str) or not argument for argument in command)
    ):
        raise ValueError("tests_pass requires test_cmd as a non-empty argv list")
    if type(min_tests) is not int or min_tests < 1:
        raise ValueError("tests_pass min_tests must be an integer greater than zero")
    is_pytest = command[0] in {"pytest", "py.test"} or (
        len(command) > 2
        and command[0] in {"python", "python3"}
        and command[1:3] == ["-m", "pytest"]
    )
    if not is_pytest:
        raise ValueError("tests_pass test_cmd must invoke pytest")
    return command.copy(), min_tests


def _junit_counts(content: bytes) -> tuple[int, int, int, int, int] | None:
    try:
        root = fromstring(content)
    except (ParseError, DefusedXmlException):
        return None
    cases = list(root.iter("testcase"))
    failures = 0
    errors = 0
    skipped = 0
    for case in cases:
        failures += int(case.find("failure") is not None)
        errors += int(case.find("error") is not None)
        skipped += int(case.find("skipped") is not None)
    passed = max(len(cases) - failures - errors - skipped, 0)
    return len(cases), passed, failures, errors, skipped


def _verdict_from_result(result: SandboxResult, min_tests: int) -> Verdict:
    if result.timed_out:
        return Verdict(
            passed=False,
            score=0,
            error_kind="timeout",
            details={"reason": "sandbox wall-clock timeout"},
        )
    if result.oom_killed:
        return Verdict(
            passed=False,
            score=0,
            error_kind="oom",
            details={"reason": "sandbox was killed for exceeding memory limit"},
        )
    junit = result.collected.get(JUNIT_PATH)
    if junit is None:
        if result.exit_code == 125:
            return _invalid_patch("git apply could not apply the patch")
        return Verdict(
            passed=False,
            score=0,
            error_kind="no_tests",
            details={"reason": "sandbox did not produce JUnit results"},
        )
    counts = _junit_counts(junit)
    if counts is None:
        return Verdict(
            passed=False,
            score=0,
            error_kind="test_failure",
            details={"reason": "sandbox produced invalid or unsafe JUnit XML"},
        )
    total, passed_tests, failures, errors, skipped = counts
    if total < min_tests:
        return Verdict(
            passed=False,
            score=passed_tests / total if total else 0,
            error_kind="no_tests",
            details={
                "reason": f"collected {total} tests; minimum is {min_tests}",
                "tests_collected": total,
                "passed_tests": passed_tests,
            },
        )
    failed = result.exit_code != 0 or failures > 0 or errors > 0
    return Verdict(
        passed=not failed,
        score=passed_tests / total,
        error_kind="test_failure" if failed else "none",
        details={
            "tests_collected": total,
            "passed_tests": passed_tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "exit_code": result.exit_code,
        },
    )


class TestsPassValidator:
    async def validate(self, context: ValidationContext) -> Verdict:
        if context.task.category != "coding":
            raise ValueError("tests_pass validator requires a coding task")
        editable_globs = context.task.validator.config.get("editable_globs")
        if (
            not isinstance(editable_globs, list)
            or not editable_globs
            or not all(isinstance(pattern, str) for pattern in editable_globs)
        ):
            raise ValueError("tests_pass requires non-empty editable_globs")
        reason = _validate_patch(context.patch, editable_globs)
        if reason is not None:
            return _invalid_patch(reason)

        test_command, min_tests = _test_command(context.task.validator.config)
        files = dict(context.files)
        files.update(_hidden_files(context))
        if any(
            path == ".agentbench-internal" or path.startswith(".agentbench-internal/")
            for path in files
        ):
            raise InfraError("task uses a reserved sandbox control path")
        files[PATCH_PATH] = context.patch
        if len(files) > MAX_TEST_FILES:
            raise InfraError("sandbox task input exceeds 500 files")
        cmd = [
            "python",
            "-c",
            _WRAPPER,
            "/workspace/" + PATCH_PATH,
            "/workspace/" + JUNIT_PATH,
            json.dumps(test_command),
        ]
        result = await context.sandbox.run(
            SANDBOX_IMAGE,
            files,
            cmd,
            context.task.limits,
            [JUNIT_PATH],
        )
        return _verdict_from_result(result, min_tests)
