"""LiteLLM custom hook for deterministic fault injection by run key metadata."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

try:
    from litellm import CustomLogger
except Exception:  # pragma: no cover - optional dependency for local runtime

    class CustomLogger:  # type: ignore[misc]
        """Fallback no-op logger when LiteLLM is unavailable."""

        pass


try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - optional dependency in test environments
    Redis = Any  # type: ignore[misc]


def _fault_plan_from_metadata(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    plan = payload.get("fault_plan")
    if isinstance(plan, Mapping):
        return dict(plan)
    return {}


def _redis_from_env() -> Any | None:
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        from redis.asyncio import Redis as RedisClient

        return RedisClient.from_url(url)
    except Exception:
        return None


class LiteLLMFaultHook(CustomLogger):
    """Raises or delays requests according to the run-scoped fault plan."""

    def __init__(self, redis_client: Any | None = None) -> None:
        self.redis_client = redis_client or _redis_from_env()

    async def async_pre_call_hook(self, *args: Any, **kwargs: Any) -> Any:
        metadata = kwargs.get("metadata")
        if metadata is None and args and isinstance(args[0], Mapping):
            metadata = args[0].get("metadata")
        if not isinstance(metadata, Mapping):
            return None
        run_id = metadata.get("run_id")
        plan = _fault_plan_from_metadata(metadata)
        if not run_id or not plan:
            return None
        redis_client = self.redis_client
        if redis_client is None:
            return None
        call_no = int(await redis_client.incr(f"run:{run_id}:calls"))
        for fault in plan.get("faults", []):
            if not isinstance(fault, Mapping):
                continue
            fault_type = str(fault.get("fault_type") or "")
            if not fault_type:
                continue
            at_call = int(fault.get("at_call", 1) or 1)
            count = int(fault.get("count", 1) or 1)
            if fault_type == "rate_limit_429" and at_call <= call_no < at_call + count:
                await redis_client.rpush(
                    f"run:{run_id}:faults",
                    json.dumps(
                        {
                            "fault_type": fault_type,
                            "ts": datetime.now(UTC).isoformat(),
                            "detail": {"at_call": at_call, "count": count},
                        }
                    ),
                )
                raise RuntimeError("rate_limit_429")
            if fault_type == "latency_spike" and call_no == at_call:
                delay = float(fault.get("delay_s") or 2.5)
                await redis_client.rpush(
                    f"run:{run_id}:faults",
                    json.dumps(
                        {
                            "fault_type": fault_type,
                            "ts": datetime.now(UTC).isoformat(),
                            "detail": {"delay_s": delay},
                        }
                    ),
                )
                await asyncio.sleep(delay)
            if fault_type == "empty_response" and call_no == at_call:
                await redis_client.rpush(
                    f"run:{run_id}:faults",
                    json.dumps(
                        {
                            "fault_type": fault_type,
                            "ts": datetime.now(UTC).isoformat(),
                            "detail": {"empty": True},
                        }
                    ),
                )
                response = {"choices": [{"message": {"content": ""}}]}
                kwargs["mock_response"] = response
                return {"mock_response": response}
            if fault_type == "error_5xx" and at_call <= call_no < at_call + count:
                await redis_client.rpush(
                    f"run:{run_id}:faults",
                    json.dumps(
                        {
                            "fault_type": fault_type,
                            "ts": datetime.now(UTC).isoformat(),
                            "detail": {"status": 500, "count": count},
                        }
                    ),
                )
                raise RuntimeError("error_5xx")
        return None
