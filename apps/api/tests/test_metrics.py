from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from agentbench_api.services.metrics import record_run_usage
from agentbench_api.services.scorer import (
    pass_at_k,
    success_rate,
    summarize_runs,
    wilson_interval,
)


def test_pass_1_matches_success_rate() -> None:
    result = pass_at_k([(10, 7)], 1)
    assert result["value"] == pytest.approx(success_rate(7, 10))
    assert result["excluded"] == 0


def test_pass_k_is_monotone_non_increasing() -> None:
    result_1 = pass_at_k([(8, 5), (10, 4)], 1)
    result_2 = pass_at_k([(8, 5), (10, 4)], 2)
    assert result_1["value"] >= result_2["value"]
    assert result_1["value"] >= 0.0
    assert result_2["value"] >= 0.0


def test_wilson_interval_is_bounded_and_narrows_with_more_trials() -> None:
    narrow = wilson_interval(90, 100)
    wide = wilson_interval(9, 10)
    assert 0.0 <= narrow[0] <= narrow[1] <= 1.0
    assert 0.0 <= wide[0] <= wide[1] <= 1.0
    assert narrow[1] - narrow[0] < wide[1] - wide[0]


def test_summary_ignores_infra_errors_for_scoring() -> None:
    summary = summarize_runs(
        [
            {"status": "completed", "passed": True},
            {"status": "completed", "passed": False},
            {"status": "agent_error", "passed": False},
            {"status": "timeout", "passed": False},
            {"status": "infra_error", "passed": False},
        ]
    )
    assert summary["success_rate"] == pytest.approx(0.25)
    assert summary["n"] == 4
    assert summary["infra_error_count"] == 1


def test_cost_metrics_include_all_spend_and_bucket_each_run() -> None:
    summary = summarize_runs(
        [
            {"status": "completed", "passed": True, "cost_usd": 0.02},
            {"status": "completed", "passed": False, "cost_usd": 0.04},
            {"status": "infra_error", "cost_usd": 0.10},
        ]
    )

    assert summary["cost_per_success_usd"] == pytest.approx(0.16)
    assert summary["mean_cost_per_run_usd"] == pytest.approx(0.16 / 3)
    assert summary["cost_distribution_usd"] == {
        "zero": 0,
        "under_0_01": 0,
        "0_01_to_0_10": 2,
        "0_10_to_1": 1,
        "1_or_more": 0,
    }


class _FakeScalarResult:
    def __init__(self, values: list[tuple[str, dict[str, object]]]) -> None:
        self.values = values

    def all(self) -> list[tuple[str, dict[str, object]]]:
        return self.values


class _FakeSession:
    def __init__(self, run: SimpleNamespace, payloads: list[dict[str, object]]) -> None:
        self.run = run
        self.payloads = payloads

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, _model: object, _run_id: object) -> SimpleNamespace:
        return self.run

    async def execute(self, _statement: object) -> _FakeScalarResult:
        return _FakeScalarResult([("llm", payload) for payload in self.payloads])

    async def commit(self) -> None:
        return None


class _FakeSessionFactory:
    def __init__(self, run: SimpleNamespace, payloads: list[dict[str, object]]) -> None:
        self.run = run
        self.payloads = payloads

    def __call__(self) -> _FakeSession:
        return _FakeSession(self.run, self.payloads)


@pytest.mark.asyncio
async def test_record_run_usage_classifies_gateway_budget_rejection(
    monkeypatch,
) -> None:
    run = SimpleNamespace(
        tokens_in=0,
        tokens_out=0,
        cost_usd=0,
        status="completed",
        verdict={"passed": True},
        failure_cause=None,
        error=None,
    )
    factory = _FakeSessionFactory(run, [{"budget_exceeded": True}])

    async def usage(*_args: object, **_kwargs: object) -> dict[str, int | float]:
        return {"tokens_in": 20, "tokens_out": 8, "cost_usd": 0.95, "calls": 2}

    monkeypatch.setattr("agentbench_api.services.metrics.get_run_usage", usage)

    await record_run_usage(
        uuid4(),
        budget_usd=1.0,
        session_factory=factory,
    )

    assert run.tokens_in == 20
    assert run.tokens_out == 8
    assert float(run.cost_usd) == pytest.approx(0.95)
    assert run.status == "agent_error"
    assert run.verdict is None
    assert run.failure_cause == "budget_exceeded"
