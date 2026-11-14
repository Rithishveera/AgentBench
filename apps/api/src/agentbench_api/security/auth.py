"""API-key and per-run callback authentication dependencies."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.deps import get_session
from agentbench_api.models import Run


async def require_api_key(
    request: Request,
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    settings = request.app.state.settings
    expected = settings.api_key.get_secret_value()
    if api_key is None or not hmac.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


async def require_run_token(
    run_id: UUID,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "running":
        raise HTTPException(status_code=409, detail="Run is not accepting callbacks")
    token = authorization.removeprefix("Bearer ") if authorization else ""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if run.token_hash is None or not hmac.compare_digest(run.token_hash, token_hash):
        raise HTTPException(status_code=403, detail="Invalid run token")
    now = datetime.now(UTC)
    if run.token_expires_at is None or run.token_expires_at <= now:
        raise HTTPException(status_code=403, detail="Run token expired")
    return run
