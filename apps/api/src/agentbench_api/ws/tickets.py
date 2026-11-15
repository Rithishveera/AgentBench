"""Single-use stream tickets issued by the BFF and verified by the WS endpoint."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING
from uuid import UUID

from redis.asyncio import Redis

if TYPE_CHECKING:
    pass

TICKET_TTL_SECONDS = 30
_PREFIX = "ws:ticket:"


def _key(token: str) -> str:
    return f"{_PREFIX}{token}"


async def create_ticket(redis: Redis, benchmark_id: UUID) -> str:
    """Generate a single-use ticket and store it in Redis with a 30s TTL."""
    token = secrets.token_urlsafe(32)
    await redis.set(_key(token), str(benchmark_id), ex=TICKET_TTL_SECONDS)
    return token


async def consume_ticket(redis: Redis, token: str, benchmark_id: UUID) -> bool:
    """Atomically verify-and-delete a ticket.

    Returns False if invalid, expired, or issued for a different benchmark.
    """
    key = _key(token)
    value: str | None = await redis.getdel(key)
    if value is None:
        return False
    return value == str(benchmark_id)
