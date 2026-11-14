"""Interfaces shared by task validators and the validation sandbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from agentbench_tasks.schema import Task, TaskLimits
from pydantic import BaseModel, ConfigDict, Field


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    score: float = Field(ge=0, le=1)
    error_kind: Literal[
        "none", "patch_invalid", "timeout", "oom", "test_failure", "no_tests"
    ]
    details: dict[str, Any]


@dataclass(slots=True)
class SandboxResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    oom: bool
    collected_files: dict[str, bytes]


@dataclass(slots=True)
class ValidationContext:
    task: Task
    files: dict[str, bytes]
    patch: bytes
    sandbox: SandboxRunner


class SandboxRunner(Protocol):
    async def run(
        self,
        image: str,
        files: dict[str, bytes],
        cmd: list[str],
        limits: TaskLimits,
        collect_paths: list[str],
    ) -> SandboxResult: ...


class Validator(Protocol):
    async def validate(self, context: ValidationContext) -> Verdict: ...


class InfraError(Exception):
    """Raised when platform infrastructure prevents a verdict."""
