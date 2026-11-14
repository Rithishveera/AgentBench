from __future__ import annotations

import asyncio
import io
import stat
import tarfile
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from agentbench_api.services.sandbox import DockerSandbox, InfraError, Limits
from agentbench_tasks.schema import TaskLimits
from pydantic import ValidationError


class _FakeContainer:
    attrs: dict[str, Any] = {"State": {"OOMKilled": False}}
    removed = False
    accepts_archive = True
    stdout = b"out"
    stderr = b"err"
    archive = b""
    archive_mode = stat.S_IFREG | 0o644

    def put_archive(self, path: str, archive: bytes) -> bool:
        return self.accepts_archive

    def start(self) -> None:
        return None

    def wait(self, timeout: int) -> dict[str, int]:
        return {"StatusCode": 0}

    def reload(self) -> None:
        return None

    def logs(self, **kwargs: Any) -> bytes:
        return self.stdout if kwargs["stdout"] else self.stderr

    def get_archive(
        self, path: str, chunk_size: int
    ) -> tuple[list[bytes], dict[str, int]]:
        return [self.archive], {"mode": self.archive_mode}

    def remove(self, force: bool) -> None:
        self.removed = True


class _FakeContainers:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.container = _FakeContainer()
        self.listed: list[_FakeContainer] = []

    def create(self, **kwargs: Any) -> _FakeContainer:
        self.created.append(kwargs)
        return self.container

    def list(self, **kwargs: Any) -> list[_FakeContainer]:
        return self.listed


class _FakeClient:
    def __init__(self) -> None:
        self.containers = _FakeContainers()


def _task_limits(timeout_s: int = 2) -> TaskLimits:
    return TaskLimits(timeout_s=timeout_s, max_steps=10, max_cost_usd=1)


def _tar_entry(name: str, content: bytes, entry_type: bytes = tarfile.REGTYPE) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.type = entry_type
        info.size = len(content) if entry_type == tarfile.REGTYPE else 0
        if entry_type == tarfile.SYMTYPE:
            info.linkname = content.decode()
        archive.addfile(
            info, io.BytesIO(content) if entry_type == tarfile.REGTYPE else None
        )
    return output.getvalue()


def test_run_rejects_traversal_before_container_creation() -> None:
    client = _FakeClient()
    sandbox = DockerSandbox(client=client)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsafe sandbox path"):
        asyncio.run(
            sandbox.run(
                "agentbench/sandbox:py312",
                {"../../etc/passwd": b"bad"},
                ["python", "-c", "pass"],
                _task_limits(),
                [],
            )
        )
    assert client.containers.created == []


def test_run_applies_container_isolation_and_removes_container() -> None:
    client = _FakeClient()
    sandbox = DockerSandbox(client=client)  # type: ignore[arg-type]
    command = ["python", "-c", "print('ok')"]
    result = asyncio.run(
        sandbox.run(
            "agentbench/sandbox:py312", {"input.txt": b"x"}, command, _task_limits(), []
        )
    )
    options = client.containers.created[0]
    assert options["command"] is command
    assert options["network_mode"] == "none"
    assert options["user"] == "10001:10001"
    assert options["read_only"] is True
    assert options["cap_drop"] == ["ALL"]
    assert options["security_opt"] == ["no-new-privileges:true"]
    assert options["pids_limit"] == 64
    assert options["mem_limit"] == options["memswap_limit"]
    assert options["nano_cpus"] == 1_000_000_000
    assert options["working_dir"] == "/workspace"
    assert all(
        "nosuid" in value and "uid=10001" in value
        for value in options["tmpfs"].values()
    )
    assert options["labels"]["agentbench.sandbox"] == "1"
    assert options["labels"]["run_id"]
    assert result.stdout == b"out"
    assert result.stderr == b"err"
    assert client.containers.container.removed is True


def test_run_removes_container_when_input_upload_fails() -> None:
    client = _FakeClient()
    client.containers.container.accepts_archive = False
    sandbox = DockerSandbox(client=client)  # type: ignore[arg-type]
    with pytest.raises(InfraError, match="rejected sandbox input"):
        asyncio.run(
            sandbox.run(
                "agentbench/sandbox:py312",
                {"input.txt": b"x"},
                ["python", "-c", "pass"],
                _task_limits(),
                [],
            )
        )
    assert client.containers.container.removed is True


def test_run_truncates_each_log_stream() -> None:
    client = _FakeClient()
    client.containers.container.stdout = b"o" * (128 * 1024)
    client.containers.container.stderr = b"e" * (128 * 1024)
    sandbox = DockerSandbox(client=client)  # type: ignore[arg-type]
    result = asyncio.run(
        sandbox.run(
            "agentbench/sandbox:py312",
            {},
            ["python", "-c", "pass"],
            _task_limits(),
            [],
        )
    )
    assert len(result.stdout) == 64 * 1024
    assert len(result.stderr) == 64 * 1024


def test_run_collects_only_requested_regular_file() -> None:
    client = _FakeClient()
    client.containers.container.archive = _tar_entry("result.txt", b"passed")
    sandbox = DockerSandbox(client=client)  # type: ignore[arg-type]
    result = asyncio.run(
        sandbox.run(
            "agentbench/sandbox:py312",
            {},
            ["python", "-c", "pass"],
            _task_limits(),
            ["result.txt"],
        )
    )
    assert result.collected == {"result.txt": b"passed"}


def test_run_rejects_symlink_from_collected_directory() -> None:
    client = _FakeClient()
    client.containers.container.archive = _tar_entry(
        "output/escape", b"../../etc/passwd", tarfile.SYMTYPE
    )
    client.containers.container.archive_mode = stat.S_IFDIR | 0o755
    sandbox = DockerSandbox(client=client)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsafe collected entry"):
        asyncio.run(
            sandbox.run(
                "agentbench/sandbox:py312",
                {},
                ["python", "-c", "pass"],
                _task_limits(),
                ["output"],
            )
        )
    assert client.containers.container.removed is True


def test_limits_reject_values_above_hard_caps() -> None:
    with pytest.raises(ValidationError):
        Limits(memory_bytes=3 * 1024 * 1024 * 1024)


def test_reap_orphans_removes_only_containers_past_cutoff() -> None:
    client = _FakeClient()
    old = _FakeContainer()
    recent = _FakeContainer()
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    old.attrs = {"Created": cutoff.isoformat()}
    recent.attrs = {"Created": datetime.now(UTC).isoformat()}
    client.containers.listed = [old, recent]
    sandbox = DockerSandbox(client=client)  # type: ignore[arg-type]
    removed = asyncio.run(sandbox.reap_orphans(older_than_s=3600))
    assert removed == 1
    assert old.removed is True
    assert recent.removed is False


def test_default_client_rejects_raw_docker_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    with pytest.raises(InfraError, match="docker-socket-proxy"):
        DockerSandbox()
