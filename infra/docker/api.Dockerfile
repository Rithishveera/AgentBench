FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/src apps/api/src
COPY packages/agent-sdk/pyproject.toml packages/agent-sdk/pyproject.toml
COPY packages/agent-sdk/src packages/agent-sdk/src
COPY packages/task-spec/pyproject.toml packages/task-spec/pyproject.toml
COPY packages/task-spec/src packages/task-spec/src
COPY suites/coding suites/coding

RUN uv sync --frozen --package agentbench-api --no-dev

ENV PATH="/workspace/.venv/bin:${PATH}"

CMD ["uvicorn", "agentbench_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]