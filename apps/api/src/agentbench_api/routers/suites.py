"""Public task-suite metadata endpoints."""

from __future__ import annotations

from typing import Annotated

from agentbench_tasks.loader import Suite, task_digest
from fastapi import APIRouter, Depends, HTTPException, Request

from agentbench_api.security.auth import require_api_key

router = APIRouter(prefix="/suites", tags=["suites"])
ApiKey = Annotated[None, Depends(require_api_key)]


def _summary(suite: Suite) -> dict[str, object]:
    return {
        "id": suite.root.name,
        "title": suite.root.name,
        "task_count": len(suite.tasks),
    }


@router.get("")
async def list_suites(request: Request, _: ApiKey) -> list[dict[str, object]]:
    suites: dict[str, Suite] = request.app.state.suites
    return [_summary(suites[suite_id]) for suite_id in sorted(suites)]


@router.get("/{suite_id}/tasks")
async def list_suite_tasks(
    suite_id: str,
    request: Request,
    _: ApiKey,
) -> list[dict[str, object]]:
    suite: Suite | None = request.app.state.suites.get(suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Suite not found")
    return [
        {
            "id": task.id,
            "title": task.title,
            "category": task.category,
            "limits": task.limits.model_dump(mode="json"),
            "digest": task_digest(task),
        }
        for task in suite.tasks
    ]
