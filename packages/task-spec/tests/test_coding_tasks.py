from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from agentbench_tasks.loader import load_suite
from agentbench_tasks.validators.tests_pass import _validate_patch

SUITES_DIR = Path(__file__).resolve().parents[3] / "suites" / "coding"


def test_coding_suite_contains_three_required_tasks() -> None:
    suite = load_suite(SUITES_DIR)
    assert {task.id for task in suite.tasks} == {
        "fix-failing-test",
        "refactor-extract-func",
        "add-feature-edge-cases",
    }


def test_reference_patches_are_allowed_unified_diffs() -> None:
    suite = load_suite(SUITES_DIR)
    for task in suite.tasks:
        assert task._task_dir is not None
        patch = (task._task_dir / "reference" / "solution.patch").read_bytes()
        editable_globs = task.validator.config["editable_globs"]
        assert _validate_patch(patch, editable_globs) is None


@pytest.mark.parametrize(
    "task_id",
    [
        "fix-failing-test",
        "refactor-extract-func",
        "add-feature-edge-cases",
    ],
)
def test_reference_patch_applies_to_fixture(task_id: str, tmp_path: Path) -> None:
    suite = load_suite(SUITES_DIR)
    task = next(task for task in suite.tasks if task.id == task_id)
    assert task._task_dir is not None
    worktree = tmp_path / task_id
    shutil.copytree(task._task_dir / "fixture", worktree)
    patch_path = task._task_dir / "reference" / "solution.patch"
    result = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", str(patch_path)],
        cwd=worktree,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
