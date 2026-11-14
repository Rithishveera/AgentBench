"""Docker-backed execution for untrusted task code."""

from __future__ import annotations

import asyncio
import os
import stat
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

import docker
import requests
from agentbench_tasks.schema import TaskLimits
from agentbench_tasks.validators.base import InfraError, SandboxResult
from docker.client import DockerClient
from docker.models.containers import Container
from pydantic import BaseModel, ConfigDict, Field

from agentbench_api.services.sandbox_archive import (
    _make_archive,
    _read_archive,
    _read_logs,
    _validate_relative_path,
)

MiB = 1024 * 1024
SANDBOX_LABEL = "agentbench.sandbox"


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_s: int = Field(default=300, ge=1, le=1800)
    memory_bytes: int = Field(default=512 * MiB, ge=64 * MiB, le=2 * 1024 * MiB)
    cpu_count: float = Field(default=1.0, gt=0, le=4)
    pids_limit: int = Field(default=64, ge=16, le=256)
    tmpfs_bytes: int = Field(default=64 * MiB, ge=MiB, le=512 * MiB)
    workspace_bytes: int = Field(default=64 * MiB, ge=MiB, le=256 * MiB)
    max_input_bytes: int = Field(default=16 * MiB, ge=1, le=128 * MiB)
    max_collect_bytes: int = Field(default=8 * MiB, ge=1, le=128 * MiB)
    nofile_limit: int = Field(default=64, ge=16, le=1024)
    file_size_limit: int = Field(default=64 * MiB, ge=MiB, le=2 * 1024 * MiB)


def _client_from_environment() -> DockerClient:
    host = os.environ.get("DOCKER_HOST", "")
    parsed = urlsplit(host)
    if (
        parsed.scheme != "tcp"
        or parsed.hostname != "docker-socket-proxy"
        or parsed.port != 2375
    ):
        raise InfraError("DOCKER_HOST must point to docker-socket-proxy:2375")
    try:
        return docker.DockerClient(base_url=host, timeout=15)
    except docker.errors.DockerException as error:
        raise InfraError(
            f"Docker sandbox client initialization failed: {type(error).__name__}"
        ) from None


class DockerSandbox:
    def __init__(
        self,
        client: DockerClient | None = None,
        limits: Limits | None = None,
    ) -> None:
        self._client = client if client is not None else _client_from_environment()
        self.limits = limits or Limits()

    async def run(
        self,
        image: str,
        files: dict[str, bytes],
        cmd: list[str],
        limits: TaskLimits,
        collect_paths: list[str],
    ) -> SandboxResult:
        return await asyncio.to_thread(
            self._run_sync, image, files, cmd, limits, collect_paths
        )

    def _run_sync(
        self,
        image: str,
        files: dict[str, bytes],
        cmd: list[str],
        task_limits: TaskLimits,
        collect_paths: list[str],
    ) -> SandboxResult:
        if not image or not isinstance(cmd, list) or not cmd:
            raise ValueError("image and non-empty command list are required")
        if any(not isinstance(argument, str) or not argument for argument in cmd):
            raise ValueError("command arguments must be non-empty strings")
        for path in collect_paths:
            _validate_relative_path(path)
        archive = _make_archive(files, self.limits.max_input_bytes)
        timeout_s = min(task_limits.timeout_s, self.limits.timeout_s)
        container: Container | None = None
        started = time.monotonic()
        try:
            container = self._client.containers.create(
                image=image,
                command=cmd,
                detach=True,
                network_mode="none",
                user="10001:10001",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                pids_limit=self.limits.pids_limit,
                mem_limit=self.limits.memory_bytes,
                memswap_limit=self.limits.memory_bytes,
                nano_cpus=int(self.limits.cpu_count * 1_000_000_000),
                ulimits=[
                    docker.types.Ulimit(
                        name="nofile",
                        soft=self.limits.nofile_limit,
                        hard=self.limits.nofile_limit,
                    ),
                    docker.types.Ulimit(
                        name="fsize",
                        soft=self.limits.file_size_limit,
                        hard=self.limits.file_size_limit,
                    ),
                ],
                tmpfs={
                    "/tmp": (
                        f"rw,nosuid,nodev,size={self.limits.tmpfs_bytes},"
                        "uid=10001,gid=10001,mode=1777"
                    ),
                    "/workspace": (
                        f"rw,nosuid,nodev,size={self.limits.workspace_bytes},"
                        "uid=10001,gid=10001,mode=0700"
                    ),
                },
                working_dir="/workspace",
                labels={SANDBOX_LABEL: "1", "run_id": uuid.uuid4().hex},
                log_config=docker.types.LogConfig(
                    type="local", config={"max-size": "256k", "max-file": "1"}
                ),
            )
            if not container.put_archive("/workspace", archive):
                raise InfraError("Docker rejected sandbox input archive")
            container.start()
            timed_out = False
            try:
                status = container.wait(timeout=timeout_s)
            except requests.exceptions.ReadTimeout:
                timed_out = True
                try:
                    container.kill()
                except docker.errors.NotFound:
                    pass
                try:
                    status = container.wait(timeout=10)
                except requests.exceptions.ReadTimeout:
                    status = {"StatusCode": -1}

            container.reload()
            state = container.attrs.get("State")
            stdout, stderr = _read_logs(container)
            collected: dict[str, bytes] = {}
            total_collected = 0
            for path in collect_paths:
                try:
                    chunks, metadata = container.get_archive(
                        f"/workspace/{path}", chunk_size=64 * 1024
                    )
                except docker.errors.NotFound:
                    continue
                if metadata is None:
                    raise InfraError("Docker returned no metadata for collected path")
                mode = metadata.get("mode")
                if isinstance(mode, int) and stat.S_IFMT(mode) == stat.S_IFLNK:
                    raise ValueError(f"collected path is a symlink: {path}")
                values = _read_archive(
                    chunks,
                    path,
                    isinstance(mode, int) and stat.S_ISDIR(mode),
                    self.limits.max_collect_bytes - total_collected,
                )
                total_collected += sum(map(len, values.values()))
                collected.update(values)
            return SandboxResult(
                exit_code=status["StatusCode"],
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                oom_killed=bool(state and state.get("OOMKilled", False)),
                duration_ms=int((time.monotonic() - started) * 1000),
                collected=collected,
            )
        except (
            docker.errors.DockerException,
            requests.exceptions.RequestException,
        ) as error:
            raise InfraError(
                f"Docker sandbox operation failed: {type(error).__name__}"
            ) from None
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except docker.errors.NotFound:
                    pass
                except docker.errors.DockerException as error:
                    raise InfraError(
                        f"Docker sandbox cleanup failed: {type(error).__name__}"
                    ) from None

    async def reap_orphans(self, older_than_s: int) -> int:
        if older_than_s < 1:
            raise ValueError("older_than_s must be positive")
        return await asyncio.to_thread(self._reap_orphans_sync, older_than_s)

    def _reap_orphans_sync(self, older_than_s: int) -> int:
        cutoff = datetime.now(UTC).timestamp() - older_than_s
        removed = 0
        try:
            containers = self._client.containers.list(
                all=True, filters={"label": f"{SANDBOX_LABEL}=1"}
            )
            for container in containers:
                created = container.attrs.get("Created")
                if not isinstance(created, str):
                    continue
                try:
                    created_at = datetime.fromisoformat(
                        created.replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    continue
                if created_at < cutoff:
                    container.remove(force=True)
                    removed += 1
        except docker.errors.DockerException as error:
            raise InfraError(
                f"Docker orphan cleanup failed: {type(error).__name__}"
            ) from None
        return removed
