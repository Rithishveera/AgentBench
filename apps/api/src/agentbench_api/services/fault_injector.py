"""Deterministic fault planning and reaction classification."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentbench_api.models import FaultEvent

_ALLOWED_FAULT_TYPES = {
    "rate_limit_429",
    "latency_spike",
    "empty_response",
    "error_5xx",
}


class FaultSpec(BaseModel):
    """Single injected fault scheduled for a specific call."""

    fault_type: str
    at_call: int = 1
    count: int = 1
    delay_s: float | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_triggered_for(self) -> bool:
        return self.count > 0


class FaultPlan(BaseModel):
    """Deterministic plan for the faults a run should see."""

    benchmark_seed: int
    run_id: str
    faults: list[FaultSpec] = Field(default_factory=list)

    @property
    def enabled(self) -> bool:
        return bool(self.faults)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "fault_plan": {
                "benchmark_seed": self.benchmark_seed,
                "faults": [fault.model_dump(mode="json") for fault in self.faults],
            },
        }


def _stable_seed(benchmark_seed: int, run_id: str | UUID) -> int:
    digest = hashlib.sha256(f"{benchmark_seed}:{run_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _extract_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _parse_flag(
    flag_value: Any,
    *,
    rng: random.Random,
    kind: str,
) -> FaultSpec | None:
    if kind == "rate_limit_429":
        if isinstance(flag_value, Mapping):
            count = max(1, _extract_int(flag_value.get("count", 1), 1))
            at_call = max(
                1,
                _extract_int(flag_value.get("at_call", 1), 1),
            )
        else:
            count = max(1, _extract_int(flag_value, 1))
            at_call = 1
        return FaultSpec(
            fault_type=kind,
            at_call=at_call,
            count=count,
            detail={"count": count, "start_call": at_call},
        )
    if kind == "latency_spike":
        delay = 2.5 if flag_value is True else float(flag_value or 2.5)
        return FaultSpec(
            fault_type=kind,
            at_call=1,
            delay_s=delay,
            detail={"delay_s": delay},
        )
    if kind == "empty_response":
        at_call = max(1, _extract_int(flag_value, 1))
        return FaultSpec(
            fault_type=kind,
            at_call=at_call,
            count=1,
            detail={"empty": True},
        )
    if kind == "error_5xx":
        count = max(1, _extract_int(flag_value, 1))
        if isinstance(flag_value, Mapping):
            at_call = max(
                1,
                _extract_int(flag_value.get("at_call", 1), 1),
            )
        else:
            at_call = 1
        return FaultSpec(
            fault_type=kind,
            at_call=at_call,
            count=count,
            detail={"status": 500, "count": count},
        )
    return None


def plan_faults(
    benchmark_seed: int,
    run_id: str | UUID,
    fault_flags: Mapping[str, Any] | None = None,
) -> FaultPlan:
    """Build a deterministic, replayable fault plan for a specific run."""
    flags = dict(fault_flags or {})
    unknown = set(flags) - _ALLOWED_FAULT_TYPES
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise ValueError(f"unsupported fault types: {unknown_list}")
    if not flags:
        return FaultPlan(benchmark_seed=benchmark_seed, run_id=str(run_id), faults=[])

    rng = random.Random(_stable_seed(benchmark_seed, str(run_id)))
    faults: list[FaultSpec] = []
    for fault_type in (
        "rate_limit_429",
        "latency_spike",
        "empty_response",
        "error_5xx",
    ):
        if fault_type not in flags:
            continue
        spec = _parse_flag(flags[fault_type], rng=rng, kind=fault_type)
        if spec is not None:
            faults.append(spec)
    faults.sort(key=lambda candidate: (candidate.at_call, candidate.fault_type))
    return FaultPlan(benchmark_seed=benchmark_seed, run_id=str(run_id), faults=faults)


def _decode_steps(steps: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    decoded: list[dict[str, Any]] = []
    for step in steps:
        payload = step.get("payload")
        if isinstance(payload, Mapping):
            record = dict(step)
            record["payload"] = dict(payload)
        else:
            record = dict(step)
        decoded.append(record)
    return decoded


def classify_reactions(
    fault_events: Sequence[Mapping[str, Any]],
    steps: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Label each fault with how the agent responded to it."""
    ordered_steps = sorted(
        _decode_steps(steps),
        key=lambda row: (
            row.get("started_at") or row.get("ts") or datetime.now(UTC).isoformat(),
            row.get("seq", 0),
        ),
    )
    labels: list[str] = []
    for event in fault_events:
        event_time = event.get("ts")
        event_type = str(event.get("fault_type") or "")
        future_steps = [
            step
            for step in ordered_steps
            if (step.get("started_at") or step.get("ts"))
            and event_time is not None
            and (step.get("started_at") or step.get("ts")) >= event_time
        ]
        if not future_steps:
            future_steps = ordered_steps
        if any(
            str(step.get("type") or "") == "retry" and bool(step.get("ok", True))
            for step in future_steps
        ):
            labels.append("retried_ok")
            continue
        if any(
            str(step.get("type") or "") in {"llm", "tool"}
            and not bool(step.get("ok", True))
            for step in future_steps
        ):
            labels.append("gave_up")
            continue
        payloads = [
            step.get("payload")
            for step in future_steps
            if isinstance(step.get("payload"), Mapping)
        ]
        if event_type in {"empty_response", "latency_spike"} and payloads:
            labels.append("degraded")
            continue
        labels.append("ignored")
    return labels


async def drain_run_faults(
    run_id: UUID | str,
    *,
    redis_client: Any | None = None,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """Drain Redis fault records and bulk-insert them as FaultEvent rows."""
    if redis_client is None or session is None:
        return []
    key = f"run:{run_id}:faults"
    raw_rows = await redis_client.lrange(key, 0, -1)
    decoded: list[dict[str, Any]] = []
    for idx, row in enumerate(raw_rows):
        if isinstance(row, (bytes, bytearray)):
            value = row.decode("utf-8")
        else:
            value = str(row)
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            payload = {"raw": value}
        if isinstance(payload, Mapping):
            record = dict(payload)
        else:
            record = {"raw": payload}
        record["run_id"] = str(run_id)
        record["seq"] = idx
        record["fault_type"] = str(record.get("fault_type") or "unknown")
        record["ts"] = record.get("ts") or datetime.now(UTC).isoformat()
        record["agent_reaction"] = record.get("agent_reaction") or "none"
        record["detail"] = cast(dict[str, Any], record.get("detail") or {})
        decoded.append(record)
    if not decoded:
        return []
    bulk_rows = [
        {
            "run_id": row["run_id"],
            "seq": row["seq"],
            "fault_type": row["fault_type"],
            "ts": (
                datetime.fromisoformat(str(row["ts"]))
                if isinstance(row["ts"], str)
                else row["ts"]
            ),
            "agent_reaction": row["agent_reaction"],
            "detail": row["detail"],
        }
        for row in decoded
    ]
    await session.execute(insert(FaultEvent), bulk_rows)
    await session.commit()
    return decoded
