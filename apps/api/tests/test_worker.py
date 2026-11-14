from __future__ import annotations

from pathlib import Path

from agentbench_api.workers.tasks import _load_suites


def test_worker_loads_suite_registry_for_visible_run_files() -> None:
    suites = _load_suites(Path("suites"))

    assert set(suites) == {"coding"}
    assert suites["coding"].tasks
