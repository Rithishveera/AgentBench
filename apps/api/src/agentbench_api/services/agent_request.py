"""Build agent requests from persisted task data and visible suite fixtures."""

from __future__ import annotations

from agentbench_sdk.schemas import (
    CallbackConfig,
    FileContent,
    RunLimits,
    RunRequest,
    RunTask,
)
from agentbench_tasks.loader import Suite, visible_files
from agentbench_tasks.schema import Task
from pydantic import AnyHttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.models import Run, TaskRecord


async def _task_model(task_record: TaskRecord) -> Task:
    return Task.model_validate(task_record.spec)


async def _run_request_for(
    session: AsyncSession,
    run: Run,
    *,
    suites: dict[str, Suite] | None = None,
) -> tuple[Task, RunRequest]:
    task_record = await session.get(TaskRecord, run.task_id)
    if task_record is None:
        raise ValueError(f"task {run.task_id} was not found")
    task = await _task_model(task_record)
    files: list[FileContent] = []
    if suites is not None:
        for suite in suites.values():
            for candidate in suite.tasks:
                if candidate.id == run.task_id:
                    files = [
                        FileContent(path=file["path"], content=file["content"])
                        for file in visible_files(candidate)
                    ]
                    break
            if files:
                break
    run_limits = RunLimits(**task.limits.model_dump(mode="json"))
    request = RunRequest(
        run_id=str(run.id),
        task=RunTask(
            id=task.id,
            category=task.category,
            prompt=task.prompt,
            files=files,
            limits=run_limits,
        ),
        callback=CallbackConfig(
            base_url=AnyHttpUrl("http://agent-ingress:8080/internal"),
            token="placeholder-token-value",
        ),
    )
    return task, request
