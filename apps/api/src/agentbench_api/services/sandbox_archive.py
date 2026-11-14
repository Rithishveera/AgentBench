"""Bounded archive and log handling for sandbox containers."""

from __future__ import annotations

import io
import tarfile
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from docker.models.containers import Container

MiB = 1024 * 1024
MAX_FILES = 500
MAX_OUTPUT_BYTES = 64 * 1024


def _validate_relative_path(path: str) -> str:
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or PureWindowsPath(path).drive
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError(f"unsafe sandbox path: {path!r}")
    return path


def _make_archive(files: dict[str, bytes], max_bytes: int) -> bytes:
    if len(files) > MAX_FILES:
        raise ValueError(f"sandbox input exceeds {MAX_FILES} files")
    total = 0
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for path, content in sorted(files.items()):
            _validate_relative_path(path)
            if not isinstance(content, bytes):
                raise ValueError("sandbox input files must contain bytes")
            total += len(content)
            if total > max_bytes:
                raise ValueError("sandbox input exceeds configured size limit")
            info = tarfile.TarInfo(path)
            info.mode = 0o644
            info.uid = 10001
            info.gid = 10001
            info.size = len(content)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def _append_bounded(target: bytearray, chunk: bytes | None) -> None:
    if chunk:
        remaining = MAX_OUTPUT_BYTES - len(target)
        if remaining > 0:
            target.extend(chunk[:remaining])


def _read_logs(container: Container) -> tuple[bytes, bytes]:
    stdout = bytearray()
    stderr = bytearray()
    _append_bounded(stdout, container.logs(stdout=True, stderr=False))
    _append_bounded(stderr, container.logs(stdout=False, stderr=True))
    return bytes(stdout), bytes(stderr)


def _read_archive(
    chunks: Any,
    requested_path: str,
    is_directory: bool,
    max_bytes: int,
) -> dict[str, bytes]:
    archive_bytes = bytearray()
    archive_limit = max_bytes + MiB
    for chunk in chunks:
        if len(archive_bytes) + len(chunk) > archive_limit:
            raise ValueError("collected archive exceeds configured size limit")
        archive_bytes.extend(chunk)

    collected: dict[str, bytes] = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as archive:
        members = archive.getmembers()
        if len(members) > MAX_FILES:
            raise ValueError(f"collected archive exceeds {MAX_FILES} files")
        for member in members:
            name = member.name.removeprefix("./")
            if name in {"", "."} and member.isdir():
                continue
            _validate_relative_path(name)
            if (
                member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError(f"unsafe collected entry: {name}")
            if not member.isfile():
                continue
            total += member.size
            if total > max_bytes:
                raise ValueError("collected files exceed configured size limit")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"cannot read collected file: {name}")
            content = source.read(member.size + 1)
            if len(content) != member.size:
                raise ValueError(f"invalid collected file size: {name}")
            if is_directory:
                requested = PurePosixPath(requested_path)
                member_path = PurePosixPath(name)
                if member_path.parts[: len(requested.parts)] == requested.parts:
                    key = member_path.as_posix()
                else:
                    key = (requested / member_path).as_posix()
            else:
                key = requested_path
            collected[key] = content
    return collected
