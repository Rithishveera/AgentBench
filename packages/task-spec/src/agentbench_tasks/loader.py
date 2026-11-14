"""Safe suite loading and tamper-evident task digests."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agentbench_tasks.schema import Task

MAX_FIXTURE_FILES = 500
MAX_FIXTURE_FILE_BYTES = 256 * 1024
MAX_VISIBLE_BYTES = 1024 * 1024


@dataclass(slots=True)
class Suite:
    root: Path
    tasks: list[Task]


def _inside(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path escapes suite directory: {path}") from error
    return resolved


def _reject_symlinks(root: Path) -> None:
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError(f"symlink is not allowed: {candidate}")
            _inside(candidate, root)


def _load_yaml(path: Path, root: Path) -> dict[str, Any]:
    safe_path = _inside(path, root)
    if safe_path.is_symlink() or not safe_path.is_file():
        raise ValueError(f"expected a regular YAML file: {path}")
    parsed = yaml.safe_load(safe_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a YAML mapping: {path}")
    return parsed


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _tree_files(directory: Path, suite_root: Path) -> list[Path]:
    if not directory.is_dir():
        raise ValueError(f"required directory is missing: {directory}")
    paths: list[Path] = []
    for current, directories, files in os.walk(directory, followlinks=False):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in [*directories, *files]:
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError(f"symlink is not allowed: {candidate}")
            _inside(candidate, suite_root)
        paths.extend(current_path / name for name in files)
    return sorted(paths, key=lambda path: path.relative_to(directory).as_posix())


def load_suite(directory: str | Path) -> Suite:
    """Load a suite and validate its task and filesystem structure."""
    supplied_root = Path(directory).absolute()
    if not supplied_root.is_dir():
        raise ValueError(f"suite directory does not exist: {directory}")
    if supplied_root.is_symlink():
        raise ValueError(f"suite directory must not be a symlink: {directory}")
    root = supplied_root.resolve(strict=True)
    _reject_symlinks(root)
    _load_yaml(root / "suite.yaml", root)

    tasks_root = _inside(root / "tasks", root)
    if not tasks_root.is_dir():
        raise ValueError("suite must contain a tasks directory")
    tasks: list[Task] = []
    task_ids: set[str] = set()
    for task_dir in sorted(tasks_root.iterdir(), key=lambda path: path.name):
        if not task_dir.is_dir():
            raise ValueError(f"expected task directory: {task_dir}")
        _inside(task_dir, root)
        raw_task = _load_yaml(task_dir / "task.yaml", root)
        try:
            _canonical_json(raw_task)
        except (TypeError, ValueError) as error:
            raise ValueError("task.yaml values must be JSON-compatible") from error
        task = Task.model_validate(raw_task)
        if task.id in task_ids:
            raise ValueError(f"duplicate task id: {task.id}")
        task_ids.add(task.id)

        fixture_files = _tree_files(task_dir / "fixture", root)
        _tree_files(task_dir / "hidden", root)
        _tree_files(task_dir / "reference", root)
        if len(fixture_files) > MAX_FIXTURE_FILES:
            raise ValueError(f"fixture exceeds {MAX_FIXTURE_FILES} files: {task.id}")
        for file_path in fixture_files:
            if not file_path.is_file():
                raise ValueError(f"fixture entry is not a regular file: {file_path}")
            if file_path.stat().st_size > MAX_FIXTURE_FILE_BYTES:
                raise ValueError(f"fixture file exceeds 256 KB: {file_path}")

        task._task_dir = task_dir
        task._task_yaml = raw_task
        tasks.append(task)
    return Suite(root=root, tasks=tasks)


def task_digest(task: Task) -> str:
    """Return the stable digest of task metadata and fixture/hidden contents."""
    if task._task_dir is None or task._task_yaml is None:
        raise ValueError("task digest requires a task loaded from a suite")
    root = task._task_dir.parent.parent.resolve(strict=True)
    files: list[tuple[str, str]] = []
    for tree_name in ("fixture", "hidden"):
        tree = task._task_dir / tree_name
        for file_path in _tree_files(tree, root):
            relative_path = file_path.relative_to(task._task_dir).as_posix()
            files.append(
                (relative_path, hashlib.sha256(file_path.read_bytes()).hexdigest())
            )
    canonical = _canonical_json(
        {"task": task._task_yaml, "files": sorted(files)},
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def visible_files(task: Task) -> list[dict[str, str]]:
    """Return only UTF-8 fixture files for transmission to an agent."""
    if task._task_dir is None:
        raise ValueError("visible files require a task loaded from a suite")
    root = task._task_dir.parent.parent.resolve(strict=True)
    files: list[dict[str, str]] = []
    total_bytes = 0
    fixture_files = _tree_files(task._task_dir / "fixture", root)
    if len(fixture_files) > MAX_FIXTURE_FILES:
        raise ValueError(f"fixture exceeds {MAX_FIXTURE_FILES} files: {task.id}")
    for file_path in fixture_files:
        relative_path = file_path.relative_to(task._task_dir / "fixture").as_posix()
        if ".." in Path(relative_path).parts or Path(relative_path).is_absolute():
            raise ValueError(f"fixture path is not relative: {relative_path}")
        content_bytes = file_path.read_bytes()
        if len(content_bytes) > MAX_FIXTURE_FILE_BYTES:
            raise ValueError(f"fixture file exceeds 256 KB: {file_path}")
        total_bytes += len(content_bytes)
        if total_bytes > MAX_VISIBLE_BYTES:
            raise ValueError("visible fixture files exceed 1 MB")
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(
                f"fixture file is not UTF-8 text: {relative_path}"
            ) from error
        if "\x00" in content:
            raise ValueError(f"fixture file is not UTF-8 text: {relative_path}")
        files.append({"path": relative_path, "content": content})
    return files
