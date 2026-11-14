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

## M3
- `TestsPassValidator.validate(context: ValidationContext) -> Verdict`: validates coding patches and grades pytest/JUnit results in one sandbox run.
- `VALIDATORS: dict[str, Validator]`: API validator registry.
- `validate_validator_types(tasks: Iterable[Task]) -> None`: startup preflight that rejects unregistered task validator types.
- `validate_run(task: Task, artifact: bytes, sandbox: SandboxRunner) -> Verdict`: builds a visible-fixture context and dispatches to the registered validator.
- `main(argv: list[str] | None = None) -> int`: QA CLI that checks reference and empty patches for every task in a suite.

## M4
- `RunRequest(...) -> RunRequest`, `StepEvent(...) -> StepEvent`, `CompleteRequest(...) -> CompleteRequest`, and `RunResult(...) -> RunResult`: strict, size-capped agent wire models.
- `create_app(handler: Handler, secret: str | bytes, max_concurrency: int = 4) -> FastAPI`: creates an authenticated external-agent server.
- `RunContext.step(event_type: StepType, payload: dict[str, Any], ...) -> None`: queues a bounded, redacted event for callback delivery.
- `RunContext.tool(name: str) -> AsyncIterator[None]`: records tool timing and exception outcome.
- `RunContext.openai_client() -> AsyncOpenAI`: creates an OpenAI-compatible client with automatic LLM/retry telemetry.
- `AgentClient.start_run(agent_url: str, secret: str | bytes, run_request: RunRequest) -> None`: sends a signed run request without following redirects.
- `serve(fn: Handler) -> None`: runs a plain async handler as an AgentBench agent.

## M5
- `Agent`, `TaskRecord`, `Benchmark`, `Run`, and `Step`: PostgreSQL ORM tables with status/category/type constraints and required indexes.
- `create_engine(settings: Settings) -> AsyncEngine`: builds the async engine with configured pool bounds.
- `get_engine() -> AsyncEngine` and `get_session_factory() -> async_sessionmaker[AsyncSession]`: cached application engine/session factory.
- `get_session() -> AsyncIterator[AsyncSession]`: FastAPI async database dependency.
- `upsert_tasks(session: AsyncSession, suite: Suite) -> int`: upserts task specs while requiring a version increase for digest changes.
- `claim_run(session: AsyncSession, run_id: UUID) -> Run | None`: atomically changes a queued run to running.
- `bulk_insert_steps(session: AsyncSession, run_id: UUID, events: list[StepEvent]) -> int`: inserts up to 100 events idempotently.
- `mark_run_terminal(session, run_id, status, ...) -> bool`: records one terminal transition and only allows verdicts for completed runs.
- `encrypt_agent_secret(secret: str, encryption_key: str | SecretStr | None = None) -> str` and `decrypt_agent_secret(encrypted_secret: str, encryption_key: str | SecretStr | None = None) -> str`: Fernet secret storage helpers.

## M6
- `create_app(settings: Settings | None = None, *, session_factory: async_sessionmaker[AsyncSession] | None = None, redis_client: Redis | None = None) -> FastAPI`: app factory with startup sync of suite metadata and strict request-size/problem JSON handling.
- `RequestSizeLimitMiddleware`: 2MB body cap and problem-JSON 413 responses.
- `validate_agent_url(url: str, allowed_hosts: tuple[str, ...] | list[str] = ()) -> PinnedAddress`: SSRF validation for agent URLs and private/metadata blocks.
- `create_pinned_transport(pinned: PinnedAddress) -> PinnedIPTransport`: DNS-pin & Host/SNI transport for agent calls.
- `redact_payload(obj: Any, secrets: Iterable[str] = ()) -> tuple[dict[str, Any], bool]`: recursively strips secrets and caps callback payload size at 64KB.
- `require_api_key(request: Request, api_key: str | None = Header(...)) -> None`: X-API-Key auth dependency.
- `require_run_token(run_id: UUID, request: Request, authorization: str | None = Header(...), session: AsyncSession = Depends(get_session)) -> Run`: bearer token auth for running callbacks.
- `register_agent(...): POST /agents`, `list_agents(...): GET /agents`, `delete_agent(...): DELETE /agents/{id}`: agent lifecycle with SSRF health check and encrypted secret return.
- `list_suites(...): GET /suites`, `list_suite_tasks(...): GET /suites/{id}/tasks`: public suite/task metadata only.
- `get_run(...): GET /runs/{id}`, `get_run_steps(...): GET /runs/{id}/steps`: run and step read endpoints.
- `ingest_steps(...)` and `complete_run(...)`: internal callback endpoints with bearer auth, redaction, bulk-insert, and Redis completion queueing.

## M7
- `BenchmarkRequest(...) -> BenchmarkRequest`, `create_benchmark(...) -> Benchmark`: validates suite/agent bounds and materializes queued benchmark runs with repetition-aware scheduling.
- `execute_run(run_id: UUID, *, ...) -> bool`: claims queued work, mints a callback token, starts the agent, waits for Redis completion, and finalizes the run verdict while invalidating the token.
- `finalize_benchmark(benchmark_id: UUID, *, ...) -> dict[str, Any]`: aggregates child run outcomes and marks the benchmark terminal after all child runs finish.
- `WorkerConfig(max_jobs=4, job_timeout=300, retries=3)` and `reaper(...)`: worker configuration and reaper entry points for queue-driven execution and stale-run cleanup.
- `POST /benchmarks` and `GET /benchmarks/{benchmark_id}`: benchmark orchestration endpoints that validate suite metadata, enqueue work, and expose benchmark state.

## M8
- `success_rate(...)`, `wilson_interval(...)`, `pass_at_k(...)`, and `summarize_runs(...)`: pure scoring utilities with infra-error exclusion, confidence intervals, and descriptive run metrics.
- `finalize_benchmark(...)`: aggregates overall and per-agent outcomes, task digests, and task-level pass counts into the benchmark summary.
- `GET /results/leaderboard`: returns latest per-agent scores using one database query, category/suite filters, and ETag caching.
- `GET /results/compare`: compares benchmark-level and per-task deltas only when suite and task digests match.
- `docs/metrics.md`: defines scoring formulas, denominator semantics, percentile calculations, and a worked example.

## M9
- `mint_run_key(run_id, allowed_models, *, max_budget_usd, ttl, settings) -> str`: creates a LiteLLM virtual key scoped to one run, model set, spend cap, and lifetime.
- `managed_run_key(...) -> AsyncIterator[str]` and `revoke_key(key, *, settings) -> None`: ensure the virtual key is revoked when run execution exits, including exceptions.
- `get_run_usage(run_id, *, settings, session_factory) -> dict[str, int | float]`: reads token counts, spend, and call count from LiteLLM spend logs using the persisted key digest.
- `record_run_usage(run_id, *, budget_usd, settings, session_factory) -> dict[str, int | float]`: persists gateway usage and turns budget rejection into `agent_error` with `failure_cause=budget_exceeded`.
- `summarize_runs(...)`: adds cost per success, mean cost per run, and cost distribution buckets to benchmark summaries.
- `GET /internal/health`: health endpoint exposed through the agent ingress alongside `/health` and `/internal/*` callbacks.
- `make check-agent-network`: runs the plain-coder image connectivity probe against the Compose network boundary.
- `infra/litellm/config.yaml`, `infra/nginx/agents.conf`, and `docs/networking.md`: env-backed gateway configuration and the agent-facing route/network policy.

## M10
- `FaultSpec(...) -> FaultSpec` and `FaultPlan(...) -> FaultPlan`: typed, replayable fault schedules tied to a benchmark seed and run ID.
- `plan_faults(benchmark_seed, run_id, fault_flags) -> FaultPlan`: deterministically schedules 429s, latency spikes, empty responses, and 5xx errors.
- `LiteLLMFaultHook.async_pre_call_hook(...)`: applies per-run faults using shared Redis call counters and records injected events for later persistence.
- `classify_reactions(fault_events, steps) -> list[str]` and `drain_run_faults(run_id, *, redis_client, session) -> list[dict[str, Any]]`: classify agent reactions and persist fault events.
- `BenchmarkRequest.paired` and `Run.fault_mode`: optionally create baseline/faulted run pairs without mixing their fault plans.
- `summarize_runs(...)`: reports resilience and recovery rate for comparable baseline/faulted runs; definitions are in `docs/metrics.md`.
- `make check`: verified with Ruff, strict Mypy, and pytest (`139 passed, 16 skipped`).
