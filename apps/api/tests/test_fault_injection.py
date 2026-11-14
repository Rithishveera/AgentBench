from __future__ import annotations

from datetime import UTC, datetime

import pytest
from agentbench_api.services.fault_injector import classify_reactions, plan_faults

from infra.litellm.faults.hook import LiteLLMFaultHook


class _FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.values: dict[str, list[str]] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def rpush(self, key: str, value: str) -> int:
        self.values.setdefault(key, []).append(value)
        return len(self.values[key])

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self.values.get(key, [])
        if end < 0:
            end = len(items) - 1
        return items[start : end + 1]


@pytest.mark.asyncio
async def test_plan_faults_is_deterministic_for_same_seed_and_run() -> None:
    first = plan_faults(9876, "run-abc", {"rate_limit_429": 2, "latency_spike": True})
    second = plan_faults(9876, "run-abc", {"rate_limit_429": 2, "latency_spike": True})
    third = plan_faults(9876, "run-def", {"rate_limit_429": 2, "latency_spike": True})

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.model_dump(mode="json") != third.model_dump(mode="json")


@pytest.mark.asyncio
async def test_fault_hook_applies_each_fault_type() -> None:
    redis = _FakeRedis()
    hook = LiteLLMFaultHook(redis_client=redis)

    rate_plan = plan_faults(42, "run-rate", {"rate_limit_429": 2})
    with pytest.raises(RuntimeError, match="rate_limit_429"):
        await hook.async_pre_call_hook(
            metadata={
                "run_id": "run-rate",
                "fault_plan": rate_plan.to_metadata()["fault_plan"],
            }
        )

    latency_plan = plan_faults(42, "run-latency", {"latency_spike": 1.25})
    before = datetime.now(UTC)
    await hook.async_pre_call_hook(
        metadata={
            "run_id": "run-latency",
            "fault_plan": latency_plan.to_metadata()["fault_plan"],
        }
    )
    after = datetime.now(UTC)
    assert after >= before
    assert redis.values["run:run-latency:faults"]

    empty_plan = plan_faults(42, "run-empty", {"empty_response": True})
    result = await hook.async_pre_call_hook(
        metadata={
            "run_id": "run-empty",
            "fault_plan": empty_plan.to_metadata()["fault_plan"],
        },
    )
    assert result == {"mock_response": {"choices": [{"message": {"content": ""}}]}}

    error_plan = plan_faults(42, "run-error", {"error_5xx": 1})
    with pytest.raises(RuntimeError, match="error_5xx"):
        await hook.async_pre_call_hook(
            metadata={
                "run_id": "run-error",
                "fault_plan": error_plan.to_metadata()["fault_plan"],
            }
        )


@pytest.mark.asyncio
async def test_fault_hook_counter_is_shared_across_workers() -> None:
    redis = _FakeRedis()
    hook_a = LiteLLMFaultHook(redis_client=redis)
    hook_b = LiteLLMFaultHook(redis_client=redis)
    plan = plan_faults(99, "worker-run", {"rate_limit_429": 3})

    with pytest.raises(RuntimeError):
        await hook_a.async_pre_call_hook(
            metadata={
                "run_id": "worker-run",
                "fault_plan": plan.to_metadata()["fault_plan"],
            }
        )
    with pytest.raises(RuntimeError):
        await hook_b.async_pre_call_hook(
            metadata={
                "run_id": "worker-run",
                "fault_plan": plan.to_metadata()["fault_plan"],
            }
        )
    assert redis.counts["run:worker-run:calls"] == 2


def test_classify_reactions_labels_retry_give_up_and_ignore() -> None:
    now = "2026-11-14T00:00:00Z"
    retry_steps = [
        {"type": "retry", "ok": True, "started_at": now},
    ]
    labels = classify_reactions(
        [{"fault_type": "error_5xx", "ts": now}],
        retry_steps,
    )
    assert labels == ["retried_ok"]

    give_up_steps = [
        {"type": "llm", "ok": False, "started_at": now},
    ]
    labels = classify_reactions(
        [{"fault_type": "error_5xx", "ts": now}],
        give_up_steps,
    )
    assert labels == ["gave_up"]

    ignored = classify_reactions(
        [{"fault_type": "latency_spike", "ts": now}],
        [{"type": "llm", "ok": True, "started_at": now, "payload": {"degraded": True}}],
    )
    assert ignored == ["degraded"]


def test_paired_runs_keep_baseline_faults_separate() -> None:
    baseline = plan_faults(123, "baseline-run", {})
    faulted = plan_faults(
        123,
        "faulted-run",
        {"error_5xx": 1, "rate_limit_429": 2},
    )

    assert baseline.enabled is False
    assert baseline.faults == []
    assert any(fault.fault_type == "error_5xx" for fault in faulted.faults)
    assert any(fault.fault_type == "rate_limit_429" for fault in faulted.faults)
