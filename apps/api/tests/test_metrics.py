from __future__ import annotations

import pytest
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
