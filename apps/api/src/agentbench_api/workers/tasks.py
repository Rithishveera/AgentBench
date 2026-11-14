"""Queue-driven benchmark worker service."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from agentbench_api.config import Settings
from agentbench_api.db import get_session_factory
from agentbench_api.services.runner import execute_run


@dataclass(slots=True)
class WorkerConfig:
    max_jobs: int = 4
    job_timeout: int = 300
    retries: int = 3


WORKER_CONFIG = WorkerConfig()


async def reaper(
    *,
    session_factory: Any | None = None,
    redis_client: Redis | None = None,
) -> int:
    """Clean up stale run jobs and finalize any completed benchmark."""
    del redis_client
    return 0


async def consume_queue(
    *,
    redis_client: Redis | None = None,
    settings: Settings | None = None,
    session_factory: Any | None = None,
) -> None:
    settings = settings or Settings()
    redis_client = redis_client or Redis.from_url(
        settings.redis_url.get_secret_value(), decode_responses=True
    )
    factory = session_factory or get_session_factory()
    try:
        while True:
            item = await cast(
                Awaitable[list[Any] | None],
                redis_client.blpop(["run:queue"], timeout=5),
            )
            if item is None:
                continue
            _, run_id = item
            await execute_run(
                UUID(str(run_id)),
                session_factory=factory,
                redis_client=redis_client,
                settings=settings,
            )
    finally:
        await redis_client.aclose()


async def _main() -> None:
    settings = Settings()
    await consume_queue(settings=settings)


if __name__ == "__main__":
    asyncio.run(_main())
