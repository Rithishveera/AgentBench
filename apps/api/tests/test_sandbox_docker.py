from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import docker
import pytest
from agentbench_api.services.sandbox import SANDBOX_LABEL, DockerSandbox, Limits
from agentbench_tasks.schema import TaskLimits

pytestmark = pytest.mark.docker

IMAGE = "agentbench/sandbox:py312"
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def docker_client() -> Iterator[docker.DockerClient]:
    client = docker.from_env()
    yield client
    client.close()


@pytest.fixture(scope="session", autouse=True)
def sandbox_image(docker_client: docker.DockerClient) -> None:
    build_logs, _ = docker_client.images.build(
        path=str(ROOT),
        dockerfile="infra/docker/sandbox.Dockerfile",
        target="sandbox",
        tag=IMAGE,
        rm=True,
    )
    for _ in build_logs:
        pass


@pytest.fixture(autouse=True)
def no_sandbox_containers_after_test(
    docker_client: docker.DockerClient,
) -> Any:
    yield
    remaining = docker_client.containers.list(
        all=True, filters={"label": f"{SANDBOX_LABEL}=1"}
    )
    for container in remaining:
        container.remove(force=True)
    assert not remaining, "sandbox containers were left behind"


def _run(
    client: docker.DockerClient,
    command: list[str],
    *,
    timeout_s: int = 10,
    limits: Limits | None = None,
) -> Any:
    sandbox = DockerSandbox(client=client, limits=limits)
    task_limits = TaskLimits(timeout_s=timeout_s, max_steps=10, max_cost_usd=1)
    return asyncio.run(sandbox.run(IMAGE, {}, command, task_limits, []))


def test_network_is_disabled_and_rootfs_is_read_only(
    docker_client: docker.DockerClient,
) -> None:
    network = _run(
        docker_client,
        [
            "python",
            "-c",
            "import socket\n"
            "try:\n"
            "    socket.gethostbyname('example.com')\n"
            "except OSError:\n"
            "    pass\n"
            "else:\n"
            "    raise SystemExit(1)\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 443), timeout=1)\n"
            "except OSError:\n"
            "    print('network-blocked')\n"
            "else:\n"
            "    raise SystemExit(2)\n",
        ],
    )
    assert network.exit_code == 0
    assert network.stdout.strip() == b"network-blocked"
    write = _run(
        docker_client,
        ["python", "-c", "from pathlib import Path; Path('/outside').write_text('x')"],
    )
    assert write.exit_code != 0


def test_container_is_non_root_and_cannot_gain_privileges(
    docker_client: docker.DockerClient,
) -> None:
    result = _run(
        docker_client,
        [
            "python",
            "-c",
            "import os; print(os.getuid()); os.setuid(0)",
        ],
    )
    assert result.stdout.strip() == b"10001"
    assert result.exit_code != 0


def test_pids_limit_contains_fork_bomb(docker_client: docker.DockerClient) -> None:
    code = (
        "import os,time\n"
        "children=[]\n"
        "while True:\n"
        "    try:\n"
        "        pid=os.fork()\n"
        "    except OSError:\n"
        "        print('pids-limit-reached')\n"
        "        break\n"
        "    if pid == 0:\n"
        "        time.sleep(2)\n"
        "        os._exit(0)\n"
        "    children.append(pid)\n"
    )
    result = _run(
        docker_client,
        ["python", "-c", code],
        timeout_s=8,
        limits=Limits(timeout_s=8, pids_limit=16),
    )
    assert result.exit_code == 0
    assert b"pids-limit-reached" in result.stdout


def test_memory_hog_is_reported_as_oom(docker_client: docker.DockerClient) -> None:
    result = _run(
        docker_client,
        ["python", "-c", "bytearray(1024 * 1024 * 1024)"],
        timeout_s=10,
        limits=Limits(timeout_s=10, memory_bytes=128 * 1024 * 1024),
    )
    assert result.oom_killed is True


def test_wall_clock_timeout_kills_and_removes_container(
    docker_client: docker.DockerClient,
) -> None:
    result = _run(
        docker_client,
        ["python", "-c", "while True:\n    pass"],
        timeout_s=1,
        limits=Limits(timeout_s=1),
    )
    assert result.timed_out is True
    assert (
        docker_client.containers.list(all=True, filters={"label": f"{SANDBOX_LABEL}=1"})
        == []
    )


def test_large_stdout_is_truncated_and_warm_overhead_is_reported(
    docker_client: docker.DockerClient,
) -> None:
    output = _run(
        docker_client,
        [
            "python",
            "-c",
            "import sys; sys.stdout.buffer.write(b'x' * (100 * 1024 * 1024))",
        ],
    )
    assert len(output.stdout) <= 64 * 1024
    warm = _run(docker_client, ["python", "-c", "pass"])
    print(f"warm sandbox overhead: {warm.duration_ms}ms")


def test_workspace_temp_write_is_available(docker_client: docker.DockerClient) -> None:
    result = _run(
        docker_client,
        [
            "python",
            "-c",
            "from pathlib import Path; Path('/workspace/file').write_text('ok'); "
            "Path('/tmp/file').write_text('ok')",
        ],
    )
    assert result.exit_code == 0
