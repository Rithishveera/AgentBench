"""Redis pub/sub fan-out hub for live benchmark progress events."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import structlog
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

logger = structlog.get_logger(__name__)

# Max bytes per WebSocket message.
MAX_MESSAGE_BYTES = 32_768
# Max queued deltas before we drop and send a fresh snapshot.
MAX_QUEUE = 64


def channel(benchmark_id: UUID) -> str:
    return f"bench:{benchmark_id}"


def encode(event: dict[str, Any]) -> str:
    return json.dumps(event, default=str)


async def publish(redis: Redis, benchmark_id: UUID, event: dict[str, Any]) -> None:
    """Publish a progress event on the benchmark channel."""
    try:
        await redis.publish(channel(benchmark_id), encode(event))
    except Exception:
        logger.warning("hub_publish_failed", benchmark_id=str(benchmark_id))


class BenchmarkHub:
    """Fan-out from a single Redis subscription to N WebSocket send queues."""

    def __init__(self, redis: Redis, benchmark_id: UUID) -> None:
        self._redis = redis
        self._benchmark_id = benchmark_id
        self._queues: list[asyncio.Queue[str | None]] = []
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._refs = 0

    async def subscribe(self) -> asyncio.Queue[str | None]:
        """Register a new subscriber queue; start the reader task on first use."""
        async with self._lock:
            q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=MAX_QUEUE)
            self._queues.append(q)
            self._refs += 1
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._reader())
        return q

    async def unsubscribe(self, q: asyncio.Queue[str | None]) -> None:
        async with self._lock:
            try:
                self._queues.remove(q)
            except ValueError:
                pass
            self._refs -= 1

    async def _reader(self) -> None:
        pubsub: PubSub = self._redis.pubsub()
        try:
            await pubsub.subscribe(channel(self._benchmark_id))
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                data: str = raw["data"]
                if len(data.encode()) > MAX_MESSAGE_BYTES:
                    logger.warning(
                        "hub_message_too_large",
                        benchmark_id=str(self._benchmark_id),
                    )
                    continue
                async with self._lock:
                    for q in list(self._queues):
                        if q.full():
                            # Drain queue and signal the consumer to resync.
                            while not q.empty():
                                q.get_nowait()
                            q.put_nowait(None)  # None = resync signal
                        else:
                            q.put_nowait(data)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("hub_reader_crashed", benchmark_id=str(self._benchmark_id))
        finally:
            try:
                await pubsub.unsubscribe(channel(self._benchmark_id))
                await pubsub.aclose()  # type: ignore[no-untyped-call]
            except Exception:
                pass


class HubRegistry:
    """Process-local registry of one BenchmarkHub per benchmark_id."""

    def __init__(self) -> None:
        self._hubs: dict[UUID, BenchmarkHub] = {}
        self._lock = asyncio.Lock()

    async def get(self, redis: Redis, benchmark_id: UUID) -> BenchmarkHub:
        async with self._lock:
            hub = self._hubs.get(benchmark_id)
            if hub is None:
                hub = BenchmarkHub(redis, benchmark_id)
                self._hubs[benchmark_id] = hub
            return hub

    async def remove(self, benchmark_id: UUID) -> None:
        async with self._lock:
            self._hubs.pop(benchmark_id, None)


# Module-level singleton — one registry per process.
registry = HubRegistry()
