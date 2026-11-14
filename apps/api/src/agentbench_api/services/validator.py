"""Registry and run entry point for task validators."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Iterable
from pathlib import Path

from agentbench_tasks.loader import Suite, load_suite, visible_files
from agentbench_tasks.schema import Task
from agentbench_tasks.validators.base import (
    InfraError,
    SandboxRunner,
    ValidationContext,
    Validator,
    Verdict,
)
from agentbench_tasks.validators.tests_pass import TestsPassValidator

from agentbench_api.services.sandbox import DockerSandbox

VALIDATORS: dict[str, Validator] = {"tests_pass": TestsPassValidator()}


def validate_validator_types(tasks: Iterable[Task]) -> None:
    unknown = sorted({task.validator.type for task in tasks} - VALIDATORS.keys())
    if unknown:
        raise RuntimeError(f"unknown validator types at startup: {', '.join(unknown)}")


async def validate_run(
    task: Task,
    artifact: bytes,
    sandbox: SandboxRunner,
) -> Verdict:
    validator = VALIDATORS.get(task.validator.type)
    if validator is None:
        raise RuntimeError(
            f"validator type was not registered at startup: {task.validator.type}"
        )
    files = {
        item["path"]: item["content"].encode("utf-8") for item in visible_files(task)
    }
    context = ValidationContext(
        task=task,
        files=files,
        patch=artifact,
        sandbox=sandbox,
    )
    return await validator.validate(context)


async def _check_suite(suite: Suite, sandbox: SandboxRunner) -> bool:
    for task in suite.tasks:
        if task._task_dir is None:
            raise RuntimeError(f"task {task.id} was not loaded from a suite")
        reference = (task._task_dir / "reference" / "solution.patch").read_bytes()
        reference_verdict = await validate_run(task, reference, sandbox)
        if not reference_verdict.passed:
            print(f"{task.id}: reference failed: {reference_verdict.model_dump()}")
            return False
        empty_verdict = await validate_run(task, b"", sandbox)
        if empty_verdict.passed:
            print(f"{task.id}: empty patch unexpectedly passed")
            return False
        print(f"{task.id}: reference passed; empty patch failed")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentbench-validator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("suites_dir", type=Path)
    arguments = parser.parse_args(argv)
    try:
        suite = load_suite(arguments.suites_dir)
        validate_validator_types(suite.tasks)
        sandbox = DockerSandbox()
        return 0 if asyncio.run(_check_suite(suite, sandbox)) else 1
    except InfraError as error:
        print(f"QA infrastructure failure: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"QA failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
