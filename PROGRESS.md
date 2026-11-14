# Progress

## M0
- `Settings() -> Settings`: loads required secrets and optional agent-host/suite settings.
- `redact_sensitive_data(logger, method_name, event_dict) -> dict[str, Any]`: recursively redacts sensitive keys and `sk-` values.
- `configure_logging() -> None`: configures structlog JSON output with redaction.

## M1
- `Task(...) -> Task`, `TaskLimits(...) -> TaskLimits`, and `TaskValidator(...) -> TaskValidator`: validate strict task metadata and coding validator configuration.
- `Suite(root: Path, tasks: list[Task]) -> Suite`: loaded suite container.
- `load_suite(directory: str | Path) -> Suite`: validates suite layout, task IDs, and fixture constraints.
- `task_digest(task: Task) -> str`: hashes canonical task metadata and sorted fixture/hidden contents.
- `visible_files(task: Task) -> list[dict[str, str]]`: returns UTF-8 fixture files only.
- `Verdict(...) -> Verdict`, `ValidationContext(...) -> ValidationContext`, and `SandboxResult(...) -> SandboxResult`: validator and sandbox data contracts.
- `Validator.validate(context: ValidationContext) -> Verdict`: asynchronous validation interface.
- `SandboxRunner.run(image, files, cmd, limits, collect_paths) -> SandboxResult`: asynchronous sandbox interface.
- `InfraError`: platform infrastructure failure exception.
- `main(argv: list[str] | None = None) -> int`: validates suites from the module CLI.

## M2
- `Limits(...) -> Limits`: immutable sandbox policy with bounded timeout, memory, CPU, PID, tmpfs, input, collection, and ulimit settings.
- `DockerSandbox(client: DockerClient | None = None, limits: Limits | None = None) -> DockerSandbox`: creates a proxy-only Docker client by default.
- `DockerSandbox.run(image: str, files: dict[str, bytes], cmd: list[str], limits: TaskLimits, collect_paths: list[str]) -> SandboxResult`: validates input, runs an isolated container, bounds output, and always removes it.
- `DockerSandbox.reap_orphans(older_than_s: int) -> int`: removes stale labeled sandbox containers.
- `SandboxResult(exit_code, stdout, stderr, timed_out, oom_killed, duration_ms, collected) -> SandboxResult`: sandbox result contract.