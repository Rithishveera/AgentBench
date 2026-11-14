"""Strict HTTP contract shared by AgentBench and external agents."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_TASK_FILES_BYTES = 1024 * 1024
MAX_PATCH_BYTES = 256 * 1024
MAX_STEP_PAYLOAD_BYTES = 64 * 1024
StepType = Literal["llm", "tool", "retry"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FileContent(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    content: str

    @field_validator("content")
    @classmethod
    def limit_file_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_TASK_FILES_BYTES:
            raise ValueError("task file exceeds 1 MB")
        if "\x00" in value:
            raise ValueError("task files must be text")
        return value


class RunLimits(StrictModel):
    timeout_s: int = Field(ge=1, le=1800)
    max_steps: int = Field(ge=1, le=500)
    max_cost_usd: float = Field(gt=0, le=50)


class RunTask(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    category: Literal["coding", "research", "support"]
    prompt: str = Field(max_length=64 * 1024)
    files: list[FileContent] = Field(max_length=500)
    limits: RunLimits


class LLMConfig(StrictModel):
    base_url: AnyHttpUrl
    api_key: str = Field(min_length=1, max_length=4096)
    model: str = Field(min_length=1, max_length=256)


class CallbackConfig(StrictModel):
    base_url: AnyHttpUrl
    token: str = Field(min_length=16, max_length=512)


class RunRequest(StrictModel):
    run_id: str = Field(min_length=1, max_length=64)
    task: RunTask
    llm: LLMConfig | None = None
    callback: CallbackConfig

    @model_validator(mode="after")
    def limit_total_file_bytes(self) -> RunRequest:
        total = sum(len(file.content.encode("utf-8")) for file in self.task.files)
        if total > MAX_TASK_FILES_BYTES:
            raise ValueError("visible task files exceed 1 MB total")
        return self


class StepEvent(StrictModel):
    seq: int = Field(ge=0)
    type: StepType
    started_at: str = Field(min_length=1, max_length=64)
    duration_ms: int = Field(ge=0, le=24 * 60 * 60 * 1000)
    ok: bool
    payload: dict[str, Any]
    truncated: bool = False

    @model_validator(mode="after")
    def limit_payload(self) -> StepEvent:
        encoded = json.dumps(
            self.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded) > MAX_STEP_PAYLOAD_BYTES:
            preview = encoded[: MAX_STEP_PAYLOAD_BYTES // 4].decode(
                "utf-8", errors="ignore"
            )
            self.payload = {"preview": preview}
            self.truncated = True
        return self


class RunResult(StrictModel):
    patch: str | None = None
    answer: str | None = Field(default=None, max_length=64 * 1024)

    @field_validator("patch")
    @classmethod
    def limit_patch_bytes(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > MAX_PATCH_BYTES:
            raise ValueError("patch exceeds 256 KB")
        return value

    @model_validator(mode="after")
    def require_output(self) -> RunResult:
        if self.patch is None and self.answer is None:
            raise ValueError("run result requires patch or answer")
        return self


class CompleteRequest(StrictModel):
    status: Literal["success", "error"]
    patch: str | None = None
    answer: str | None = Field(default=None, max_length=64 * 1024)
    error: str | None = Field(default=None, max_length=1024)
    steps_dropped: int = Field(default=0, ge=0)

    @field_validator("patch")
    @classmethod
    def limit_patch_bytes(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > MAX_PATCH_BYTES:
            raise ValueError("patch exceeds 256 KB")
        return value

    @model_validator(mode="after")
    def validate_status_fields(self) -> CompleteRequest:
        if self.status == "success" and self.patch is None and self.answer is None:
            raise ValueError("successful completion requires patch or answer")
        if self.status == "error" and not self.error:
            raise ValueError("failed completion requires an error message")
        return self
