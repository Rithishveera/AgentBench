"""Pure scoring utilities for benchmark summaries."""

from __future__ import annotations

from collections.abc import Sequence
from math import comb, sqrt
from typing import Any


def success_rate(passed: int, n: int) -> float:
    if n <= 0:
        return 0.0
    return passed / n


def wilson_interval(
    successes: int,
    trials: int,
    *,
    z: float = 1.96,
) -> tuple[float, float]:
    if trials <= 0:
        return (0.0, 0.0)
    p = successes / trials
    center = p + (z * z) / (2 * trials)
    margin = z * sqrt((p * (1 - p) + (z * z) / (4 * trials)) / trials)
    denominator = 1 + (z * z) / trials
    lower = (center - margin) / denominator
    upper = (center + margin) / denominator
    return (max(0.0, min(1.0, lower)), max(0.0, min(1.0, upper)))


def pass_at_k(
    task_stats: Sequence[tuple[int, int]],
    k: int,
) -> dict[str, float | int]:
    if k < 1:
        raise ValueError("k must be at least 1")
    valid = [stats for stats in task_stats if stats[0] >= k]
    excluded = len(task_stats) - len(valid)
    if not valid:
        return {"value": 0.0, "excluded": excluded, "n": 0}
    total = sum(comb(passes, k) / comb(attempts, k) for attempts, passes in valid)
    return {
        "value": float(total / len(valid)),
        "excluded": excluded,
        "n": len(valid),
    }


def _nearest_rank(values: Sequence[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, int(__import__("math").ceil((percentile / 100) * len(ordered))))
    return ordered[min(rank - 1, len(ordered) - 1)]


def _failure_cause(run: dict[str, Any]) -> str:
    status = str(run.get("status") or "")
    if status == "timeout":
        return "timeout"
    if status == "agent_error":
        return "agent_error"
    if status == "infra_error":
        return "infra_error"
    explicit = str(run.get("failure_cause") or "").strip()
    if explicit:
        return explicit
    if status == "completed":
        return "test_failure" if not bool(run.get("passed", False)) else "none"
    return "test_failure"


def _cost_distribution(values: Sequence[float]) -> dict[str, int]:
    buckets = {
        "zero": 0,
        "under_0_01": 0,
        "0_01_to_0_10": 0,
        "0_10_to_1": 0,
        "1_or_more": 0,
    }
    for value in values:
        if value == 0:
            buckets["zero"] += 1
        elif value < 0.01:
            buckets["under_0_01"] += 1
        elif value < 0.10:
            buckets["0_01_to_0_10"] += 1
        elif value < 1:
            buckets["0_10_to_1"] += 1
        else:
            buckets["1_or_more"] += 1
    return buckets


def summarize_runs(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    scored = [
        run
        for run in runs
        if str(run.get("status") or "") in {"completed", "agent_error", "timeout"}
    ]
    total = len(scored)
    passed = sum(
        1
        for run in scored
        if str(run.get("status") or "") == "completed"
        and bool(run.get("passed", False))
    )
    score = success_rate(passed, total)
    lower, upper = wilson_interval(passed, total)
    infra_error_count = sum(
        1 for run in runs if str(run.get("status") or "") == "infra_error"
    )
    baseline = [run for run in runs if str(run.get("fault_mode") or "") == "none"]
    faulted = [run for run in runs if str(run.get("fault_mode") or "") == "faulted"]
    if baseline:
        baseline_passed = sum(
            1
            for run in baseline
            if str(run.get("status") or "") == "completed"
            and bool(run.get("passed", False))
        )
        baseline_total = len(
            [
                run
                for run in baseline
                if str(run.get("status") or "")
                in {"completed", "agent_error", "timeout"}
            ]
        )
        baseline_rate = success_rate(baseline_passed, baseline_total)
    else:
        baseline_rate = 0.0
    if faulted:
        faulted_passed = sum(
            1
            for run in faulted
            if str(run.get("status") or "") == "completed"
            and bool(run.get("passed", False))
        )
        faulted_total = len(
            [
                run
                for run in faulted
                if str(run.get("status") or "")
                in {"completed", "agent_error", "timeout"}
            ]
        )
        faulted_rate = success_rate(faulted_passed, faulted_total)
    else:
        faulted_rate = 0.0
    resilience = faulted_rate / baseline_rate if baseline_rate > 0.0 else 0.0
    faulted_runs = [
        run for run in runs if str(run.get("fault_mode") or "") == "faulted"
    ]
    recovery_events = [
        str(run.get("agent_reaction") or "")
        for run in faulted_runs
        if str(run.get("agent_reaction") or "") == "retried_ok"
    ]
    recovery_rate = len(recovery_events) / len(faulted_runs) if faulted_runs else 0.0
    failure_counts: dict[str, int] = {}
    for run in runs:
        cause = _failure_cause(run)
        if cause == "none":
            continue
        failure_counts[cause] = failure_counts.get(cause, 0) + 1
    duration_values = [
        int(run.get("duration_ms") or 0)
        for run in runs
        if run.get("duration_ms") is not None
    ]
    steps = [
        int(run.get("steps_count") or 0)
        for run in runs
        if run.get("steps_count") is not None
    ]
    tool_calls = [
        int(run.get("tool_calls") or 0)
        for run in runs
        if run.get("tool_calls") is not None
    ]
    costs = [
        float(run.get("cost_usd") or 0.0)
        for run in runs
        if run.get("cost_usd") is not None
    ]
    total_cost = sum(costs)
    return {
        "success_rate": float(score),
        "ci": [float(lower), float(upper)],
        "n": total,
        "passed": passed,
        "completed": sum(
            1 for run in runs if str(run.get("status") or "") == "completed"
        ),
        "agent_error_count": sum(
            1 for run in runs if str(run.get("status") or "") == "agent_error"
        ),
        "timeout_count": sum(
            1 for run in runs if str(run.get("status") or "") == "timeout"
        ),
        "infra_error_count": infra_error_count,
        "resilience": resilience,
        "recovery_rate": recovery_rate,
        "failure_causes": failure_counts,
        "cost_per_success_usd": (total_cost / passed) if passed else 0.0,
        "mean_cost_per_run_usd": (total_cost / len(costs)) if costs else 0.0,
        "cost_distribution_usd": _cost_distribution(costs),
        "duration_ms": {
            "p50": _nearest_rank(duration_values, 50),
            "p95": _nearest_rank(duration_values, 95),
            "mean": (
                (sum(duration_values) / len(duration_values))
                if duration_values
                else 0.0
            ),
        },
        "steps_mean": (sum(steps) / len(steps)) if steps else 0.0,
        "tool_calls_mean": (sum(tool_calls) / len(tool_calls)) if tool_calls else 0.0,
    }
