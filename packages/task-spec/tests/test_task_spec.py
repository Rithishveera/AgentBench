from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import agentbench_tasks.loader as loader_module
import pytest
import yaml
from agentbench_tasks import Task, load_suite, task_digest, visible_files
from agentbench_tasks.__main__ import main
from agentbench_tasks.validators.base import InfraError, Verdict
from pydantic import ValidationError


def _task_data(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "example-task",
        "category": "coding",
        "version": 1,
        "title": "Example",
        "prompt": "Make the tests pass.",
        "limits": {"timeout_s": 30, "max_steps": 10, "max_cost_usd": 1},
        "validator": {
            "type": "pytest",
            "config": {"editable_globs": ["src/**"], "test_cmd": ["pytest", "-q"]},
        },
    }
    data.update(changes)
    return data


def _write_task(
    root: Path,
    task_id: str = "example-task",
    *,
    task_data: dict[str, Any] | None = None,
    fixture: dict[str, bytes] | None = None,
    hidden: dict[str, bytes] | None = None,
    reference: dict[str, bytes] | None = None,
) -> Path:
    task_dir = root / "tasks" / task_id
    for dirname in ("fixture", "hidden", "reference"):
        (task_dir / dirname).mkdir(parents=True, exist_ok=True)
    (task_dir / "task.yaml").write_text(
        yaml.safe_dump(task_data or _task_data(id=task_id), sort_keys=False),
        encoding="utf-8",
    )
    for dirname, files in (
        ("fixture", fixture or {"same.txt": b"visible"}),
        ("hidden", hidden or {"hidden.txt": b"hidden"}),
        ("reference", reference or {"solution.patch": b"reference"}),
    ):
        for relative, content in files.items():
            target = task_dir / dirname / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    return task_dir


def _write_suite(root: Path, task_ids: tuple[str, ...] = ("example-task",)) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "suite.yaml").write_text("{}\n", encoding="utf-8")
    for task_id in task_ids:
        _write_task(root, task_id)
    return root


def test_good_suite_loads_and_visible_files_exclude_hidden_and_reference(
    tmp_path: Path,
) -> None:
    root = tmp_path / "suite"
    task_dir = _write_task(
        root,
        fixture={"same.txt": b"fixture-only"},
        hidden={"same.txt": b"hidden-secret"},
        reference={"same.txt": b"reference-secret"},
    )
    (root / "suite.yaml").write_text("{}\n", encoding="utf-8")

    suite = load_suite(root)
    assert len(suite.tasks) == 1
    task = suite.tasks[0]
    assert task.id == "example-task"
    assert visible_files(task) == [{"path": "same.txt", "content": "fixture-only"}]
    assert "hidden-secret" not in str(visible_files(task))
    assert "reference-secret" not in str(visible_files(task))
    assert task_dir.exists()


def test_load_suite_rejects_unknown_task_field(tmp_path: Path) -> None:
    root = _write_suite(tmp_path / "suite")
    task_yaml = root / "tasks" / "example-task" / "task.yaml"
    data = yaml.safe_load(task_yaml.read_text(encoding="utf-8"))
    data["unknown"] = True
    task_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_suite(root)


def test_load_suite_rejects_non_json_task_yaml_values(tmp_path: Path) -> None:
    root = _write_suite(tmp_path / "suite")
    task_yaml = root / "tasks" / "example-task" / "task.yaml"
    data = yaml.safe_load(task_yaml.read_text(encoding="utf-8"))
    data["validator"]["config"]["date"] = date(2026, 11, 14)
    task_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON-compatible"):
        load_suite(root)


def test_coding_task_requires_editable_globs(tmp_path: Path) -> None:
    data = _task_data(validator={"type": "pytest", "config": {"test_cmd": ["pytest"]}})
    with pytest.raises(ValidationError, match="editable_globs"):
        Task.model_validate(data)


def test_coding_task_rejects_shell_string_test_cmd() -> None:
    data = _task_data()
    data["validator"]["config"]["test_cmd"] = "pytest -q"
    with pytest.raises(ValidationError, match="test_cmd"):
        Task.model_validate(data)


def test_task_model_rejects_path_traversal_in_editable_glob() -> None:
    data = _task_data()
    data["validator"]["config"]["editable_globs"] = ["../hidden/**"]
    with pytest.raises(ValidationError, match="traverse"):
        Task.model_validate(data)


def test_load_suite_rejects_duplicate_task_ids(tmp_path: Path) -> None:
    root = _write_suite(tmp_path / "suite", ("example-task", "other-task"))
    duplicate = root / "tasks" / "other-task" / "task.yaml"
    data = yaml.safe_load(duplicate.read_text(encoding="utf-8"))
    data["id"] = "example-task"
    duplicate.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate task id"):
        load_suite(root)


def test_load_suite_rejects_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_suite(tmp_path / "suite")
    link = root / "tasks" / "example-task" / "fixture" / "outside.txt"
    link.write_text("outside", encoding="utf-8")
    original_is_symlink = Path.is_symlink

    def is_symlink(path: Path) -> bool:
        return path == link or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)
    with pytest.raises(ValueError, match="symlink"):
        load_suite(root)


def test_visible_files_rejects_traversal_from_fixture_to_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_suite(tmp_path / "suite")
    task = load_suite(root).tasks[0]
    fixture_dir = root / "tasks" / "example-task" / "fixture"
    hidden_file = fixture_dir / ".." / "hidden" / "hidden.txt"
    monkeypatch.setattr(
        loader_module, "_tree_files", lambda directory, suite_root: [hidden_file]
    )
    with pytest.raises(ValueError, match="fixture path is not relative"):
        visible_files(task)


def test_load_suite_rejects_binary_fixture(tmp_path: Path) -> None:
    root = _write_suite(tmp_path / "suite")
    fixture = root / "tasks" / "example-task" / "fixture" / "image.bin"
    fixture.write_bytes(b"\xff\x00")
    with pytest.raises(ValueError, match="UTF-8 text"):
        visible_files(load_suite(root).tasks[0])


def test_digest_is_independent_of_creation_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "suite.yaml").write_text("{}\n", encoding="utf-8")
    (second / "suite.yaml").write_text("{}\n", encoding="utf-8")
    _write_task(
        second,
        fixture={"z.txt": b"z", "a.txt": b"a"},
        hidden={"z.txt": b"h-z", "a.txt": b"h-a"},
    )
    _write_task(
        first,
        fixture={"a.txt": b"a", "z.txt": b"z"},
        hidden={"a.txt": b"h-a", "z.txt": b"h-z"},
    )
    assert task_digest(load_suite(first).tasks[0]) == task_digest(
        load_suite(second).tasks[0]
    )


def test_digest_changes_when_hidden_or_task_yaml_changes(tmp_path: Path) -> None:
    root = _write_suite(tmp_path / "suite")
    task_dir = root / "tasks" / "example-task"
    original = task_digest(load_suite(root).tasks[0])
    (task_dir / "hidden" / "hidden.txt").write_bytes(b"changed")
    hidden_changed = task_digest(load_suite(root).tasks[0])
    assert hidden_changed != original
    (task_dir / "task.yaml").write_text(
        yaml.safe_dump(_task_data(title="Changed")), encoding="utf-8"
    )
    assert task_digest(load_suite(root).tasks[0]) != hidden_changed


def test_visible_files_rejects_unloaded_task() -> None:
    with pytest.raises(ValueError, match="loaded from a suite"):
        visible_files(Task.model_validate(_task_data()))


def test_task_digest_rejects_unloaded_task() -> None:
    with pytest.raises(ValueError, match="loaded from a suite"):
        task_digest(Task.model_validate(_task_data()))


def test_verdict_rejects_score_outside_range() -> None:
    with pytest.raises(ValidationError):
        Verdict(passed=False, score=1.1, error_kind="test_failure", details={})


def test_infra_error_is_an_exception_type() -> None:
    assert issubclass(InfraError, Exception)


def test_cli_prints_task_id_and_digest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _write_suite(tmp_path / "suite")
    assert main(["validate", str(root)]) == 0
    assert capsys.readouterr().out.startswith("example-task ")


def test_cli_returns_one_for_invalid_suite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate", str(tmp_path / "missing")]) == 1
    assert "validation failed" in capsys.readouterr().err


def test_cli_validates_each_suite_under_suites_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suites_dir = tmp_path / "suites"
    _write_suite(suites_dir / "first")
    _write_suite(suites_dir / "second", ("other-task",))
    assert main(["validate", str(suites_dir)]) == 0
    output = capsys.readouterr().out
    assert "example-task " in output
    assert "other-task " in output
