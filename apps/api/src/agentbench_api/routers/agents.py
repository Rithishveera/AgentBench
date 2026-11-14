"""Agent registration and management endpoints."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.crypto import encrypt_agent_secret
from agentbench_api.deps import get_session
from agentbench_api.models import Agent, Run
from agentbench_api.security.auth import require_api_key
from agentbench_api.security.ssrf import create_pinned_transport, validate_agent_url

router = APIRouter(prefix="/agents", tags=["agents"])
ApiKey = Annotated[None, Depends(require_api_key)]
Session = Annotated[AsyncSession, Depends(get_session)]


class AgentRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    category: Literal["coding", "research", "support"]
    framework_tag: str | None = Field(default=None, max_length=100)
    max_concurrency: int = Field(default=2, ge=1, le=100)


def _agent_public(agent: Agent) -> dict[str, object]:
    return {
        "id": agent.id,
        "name": agent.name,
        "url": agent.url,
        "category": agent.category,
        "framework_tag": agent.framework_tag,
        "max_concurrency": agent.max_concurrency,
        "created_at": agent.created_at,
        "last_health_check_at": agent.last_health_check_at,
    }


@router.post("", status_code=201)
async def register_agent(
    body: AgentRegistration,
    request: Request,
    session: Session,
    _: ApiKey,
) -> dict[str, object]:
    settings = request.app.state.settings
    try:
        pinned = await asyncio.to_thread(
            validate_agent_url, body.url, tuple(settings.allowed_agent_hosts)
        )
        async with httpx.AsyncClient(
            transport=create_pinned_transport(pinned),
            follow_redirects=False,
            timeout=httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=2.0),
        ) as client:
            response = await client.get(body.url.rstrip("/") + "/health")
    except (ValueError, httpx.HTTPError):
        raise HTTPException(
            status_code=422,
            detail="Agent URL is invalid or unhealthy",
        ) from None
    if response.status_code != 200:
        raise HTTPException(status_code=422, detail="Agent health check failed")

    secret = secrets.token_urlsafe(32)
    agent = Agent(
        name=body.name,
        url=body.url.rstrip("/"),
        category=body.category,
        framework_tag=body.framework_tag,
        max_concurrency=body.max_concurrency,
        secret_encrypted=encrypt_agent_secret(secret, settings.encryption_key),
        last_health_check_at=datetime.now(UTC),
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return {**_agent_public(agent), "secret": secret}


@router.get("")
async def list_agents(
    session: Session,
    _: ApiKey,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    statement = select(Agent).order_by(Agent.id).limit(limit + 1)
    if cursor is not None:
        statement = statement.where(Agent.id > cursor)
    agents = list((await session.scalars(statement)).all())
    has_more = len(agents) > limit
    page = agents[:limit]
    return {
        "items": [_agent_public(agent) for agent in page],
        "next_cursor": str(page[-1].id) if has_more and page else None,
    }


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: UUID, session: Session, _: ApiKey) -> Response:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    has_runs = await session.scalar(
        select(Run.id).where(Run.agent_id == agent_id).limit(1)
    )
    if has_runs is not None:
        raise HTTPException(status_code=409, detail="Agent has benchmark runs")
    await session.delete(agent)
    await session.commit()
    return Response(status_code=204)
