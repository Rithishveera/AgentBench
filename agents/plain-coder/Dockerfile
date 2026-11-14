FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/agent-sdk/pyproject.toml packages/agent-sdk/pyproject.toml
COPY packages/task-spec/pyproject.toml packages/task-spec/pyproject.toml
COPY packages/agent-sdk/src packages/agent-sdk/src
COPY agents/plain-coder/agent.py agents/plain-coder/agent.py
COPY agents/plain-coder/network_probe.py agents/plain-coder/network_probe.py

RUN uv sync --frozen --package agentbench-sdk --no-dev

ENV PATH="/workspace/.venv/bin:${PATH}"
EXPOSE 8000
CMD ["python", "agents/plain-coder/agent.py"]
