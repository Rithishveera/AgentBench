"""WebSocket endpoint for live benchmark progress streaming."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.deps import get_session
from agentbench_api.models import Benchmark
from agentbench_api.security.auth import require_api_key
from agentbench_api.ws.hub import registry
from agentbench_api.ws.snapshot import build_snapshot
from agentbench_api.ws.tickets import consume_ticket, create_ticket

router = APIRouter(tags=["ws"])
Session = Annotated[AsyncSession, Depends(get_session)]
ApiKey = Annotated[None, Depends(require_api_key)]
logger = structlog.get_logger(__name__)

PING_INTERVAL = 20  # seconds between pings


@router.post("/benchmarks/{benchmark_id}/stream-ticket", status_code=200)
async def issue_stream_ticket(
    benchmark_id: UUID,
    request: Request,
    session: Session,
    _: ApiKey,
) -> dict[str, str]:
    """Issue a single-use ticket valid 30 s. Called by the Next.js BFF server."""
    benchmark = await session.get(Benchmark, benchmark_id)
    if benchmark is None:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    redis = request.app.state.redis
    token = await create_ticket(redis, benchmark_id)
    return {"ticket": token}


@router.websocket("/benchmarks/{benchmark_id}/stream")
async def benchmark_stream(
    websocket: WebSocket,
    benchmark_id: UUID,
    request: Request,
    session: Session,
    ticket: Annotated[str, Query()] = "",
) -> None:
    """
    WebSocket stream for live benchmark progress.
    Clients must supply ?ticket=<token> (issued by POST /stream-ticket).
    """
    redis = request.app.state.redis

    # Verify and burn ticket before accepting.
    if not ticket or not await consume_ticket(redis, ticket, benchmark_id):
        await websocket.close(code=4401)
        return

    # Verify benchmark exists.
    benchmark = await session.get(Benchmark, benchmark_id)
    if benchmark is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()

    # Send full snapshot immediately.
    snapshot = await build_snapshot(session, benchmark_id)
    if snapshot is None:
        await websocket.close(code=4404)
        return
    await _send_json(websocket, snapshot)

    # If already terminal, close cleanly — no need to subscribe.
    if benchmark.status in {"completed", "failed"}:
        await websocket.close(code=1000)
        return

    hub = await registry.get(redis, benchmark_id)
    q = await hub.subscribe()
    try:
        await _stream_loop(websocket, q, session, benchmark_id)
    finally:
        await hub.unsubscribe(q)


async def _stream_loop(
    websocket: WebSocket,
    q: asyncio.Queue[str | None],
    session: AsyncSession,
    benchmark_id: UUID,
) -> None:
    while websocket.client_state == WebSocketState.CONNECTED:
        try:
            msg = await asyncio.wait_for(q.get(), timeout=PING_INTERVAL)
        except TimeoutError:
            # Send a ping to keep the connection alive.
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
            except (WebSocketDisconnect, RuntimeError):
                return
            continue
        except asyncio.CancelledError:
            return

        if msg is None:
            # Resync signal from hub (slow client, queue was dropped).
            snapshot = await build_snapshot(session, benchmark_id)
            if snapshot is None:
                return
            try:
                await _send_json(websocket, snapshot)
            except (WebSocketDisconnect, RuntimeError):
                return
            # If the benchmark is now terminal, close.
            if snapshot["benchmark"]["status"] in {"completed", "failed"}:
                await websocket.close(code=1000)
                return
            continue

        try:
            await websocket.send_text(msg)
        except (WebSocketDisconnect, RuntimeError):
            return

        # Close cleanly if the event signals benchmark completion.
        try:
            parsed = json.loads(msg)
        except (ValueError, TypeError):
            parsed = {}

        if parsed.get("benchmark_status") in {"completed", "failed"}:
            await websocket.close(code=1000)
            return


async def _send_json(websocket: WebSocket, data: object) -> None:
    text = json.dumps(data, default=str)
    await websocket.send_text(text)
