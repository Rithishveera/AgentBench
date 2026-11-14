"""Validated task metadata models."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class TaskLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_s: int = Field(ge=1, le=1800)
    max_steps: int = Field(ge=1, le=500)
    max_cost_usd: float = Field(gt=0, le=50)


class TaskValidator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    config: dict[str, Any]


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)
    category: Literal["coding", "research", "support"]
    version: int = Field(ge=1)
    title: str
    prompt: str
    limits: TaskLimits
    validator: TaskValidator
    tags: list[str] = Field(default_factory=list)

    _task_dir: Path | None = PrivateAttr(default=None)
    _task_yaml: dict[str, Any] | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def validate_coding_config(self) -> Task:
        if self.category == "coding":
            editable_globs = self.validator.config.get("editable_globs")
            test_cmd = self.validator.config.get("test_cmd")
            if not isinstance(editable_globs, list) or not editable_globs:
                raise ValueError(
                    "coding validator config requires non-empty editable_globs"
                )
            if any(
                not isinstance(pattern, str) or not pattern
                for pattern in editable_globs
            ):
                raise ValueError("editable_globs must contain non-empty strings")
            if any(
                ".." in PurePosixPath(pattern.replace("\\", "/")).parts
                or PurePosixPath(pattern.replace("\\", "/")).is_absolute()
                or PureWindowsPath(pattern).drive
                for pattern in editable_globs
            ):
                raise ValueError("editable_globs must not traverse outside the task")
            if not isinstance(test_cmd, list) or not test_cmd:
                raise ValueError(
                    "coding validator config requires test_cmd as a non-empty list"
                )
            if any(
                not isinstance(argument, str) or not argument for argument in test_cmd
            ):
                raise ValueError("test_cmd must contain non-empty strings")
        return self
