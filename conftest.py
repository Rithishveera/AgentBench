from __future__ import annotations

import subprocess

import pytest


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if _docker_available():
        return
    skip_docker = pytest.mark.skip(reason="Docker daemon is not available")
    for item in items:
        if "docker" in item.keywords:
            item.add_marker(skip_docker)
