from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import agentbench_api.services.validator as validator_service
import docker
import pytest
import yaml
from agentbench_api.services.sandbox import DockerSandbox
from agentbench_tasks.loader import load_suite
from agentbench_tasks.validators.base import InfraError, SandboxResult
from agentbench_tasks.validators.tests_pass import JUNIT_PATH, PATCH_PATH

SUITES_DIR = Path(__file__).resolve().parents[3] / "suites" / "coding"


class _QaSandbox:
    def __init__(self) -> None:
        self.calls: list[dict[str, bytes]] = []

    async def run(
        self,
        image: str,
        files: dict[str, bytes],
        cmd: list[str],
        limits: Any,
        collect_paths: list[str],
    ) -> SandboxResult:
        self.calls.append(files)
        patch = files[PATCH_PATH]
        if patch:
            junit = (
                b"<testsuite><testcase/><testcase/><testcase/><testcase/></testsuite>"
            )
            exit_code = 0
        else:
            junit = b"<testsuite><testcase><failure/></testcase></testsuite>"
            exit_code = 1
        return SandboxResult(
            exit_code=exit_code,
            stdout=b"",
            stderr=b"",
            timed_out=False,
            oom_killed=False,
            duration_ms=1,
            collected={JUNIT_PATH: junit},
        )


def test_qa_command_checks_reference_and_empty_patch_for_each_task(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox = _QaSandbox()
    monkeypatch.setattr(validator_service, "DockerSandbox", lambda: sandbox)
    assert validator_service.main(["check", str(SUITES_DIR)]) == 0
    output = capsys.readouterr().out
    assert output.count("reference passed; empty patch failed") == 3
    assert len(sandbox.calls) == 6
    for index, files in enumerate(sandbox.calls):
        assert bool(files[PATCH_PATH]) is (index % 2 == 0)
        assert "tests/test_hidden.py" in files


def test_unknown_validator_fails_preflight_before_sandbox_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_source = SUITES_DIR
    suite_root = tmp_path / "suite"
    import shutil

    shutil.copytree(suite_source, suite_root)
    task_yaml = suite_root / "tasks" / "fix-failing-test" / "task.yaml"
    task_data = yaml.safe_load(task_yaml.read_text(encoding="utf-8"))
    task_data["validator"]["type"] = "unknown-validator"
    task_yaml.write_text(yaml.safe_dump(task_data), encoding="utf-8")

    def unexpected_sandbox() -> None:
        raise AssertionError("sandbox was constructed before registry preflight")

    monkeypatch.setattr(validator_service, "DockerSandbox", unexpected_sandbox)
    assert validator_service.main(["check", str(suite_root)]) == 1
    assert "unknown validator types at startup" in capsys.readouterr().err


def test_validate_run_uses_only_registered_validator_types() -> None:
    suite = load_suite(SUITES_DIR)
    validator_service.validate_validator_types(suite.tasks)
    assert {task.validator.type for task in suite.tasks} == {"tests_pass"}


def test_unavailable_docker_endpoint_raises_infraerror() -> None:
    task = load_suite(SUITES_DIR).tasks[0]
    sandbox = DockerSandbox(
        client=docker.DockerClient(
            base_url="http://127.0.0.1:1", version="1.41", timeout=1
        )
    )
    with pytest.raises(InfraError):
        asyncio.run(validator_service.validate_run(task, b"", sandbox))
