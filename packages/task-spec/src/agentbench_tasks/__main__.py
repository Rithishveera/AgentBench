"""Validate and print the tasks found in a suite directory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentbench_tasks.loader import load_suite, task_digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentbench_tasks")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("suites_dir", type=Path)
    arguments = parser.parse_args(argv)
    try:
        suites_dir = arguments.suites_dir
        suite_dirs = (
            [suites_dir]
            if (suites_dir / "suite.yaml").is_file()
            else sorted(path for path in suites_dir.iterdir() if path.is_dir())
        )
        if not suite_dirs:
            raise ValueError(f"no suites found in {suites_dir}")
        for suite_dir in suite_dirs:
            suite = load_suite(suite_dir)
            for task in suite.tasks:
                print(f"{task.id} {task_digest(task)}")
    except Exception as error:
        print(f"validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
