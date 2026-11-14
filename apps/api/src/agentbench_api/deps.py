"""FastAPI dependencies shared by API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.db import get_session_factory


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = (
        request.app.state.session_factory
        if hasattr(request.app.state, "session_factory")
        else get_session_factory()
    )
    async with factory() as session:
        yield session
