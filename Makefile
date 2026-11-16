.PHONY: up down check test fmt sandbox-image qa-tasks migrate check-agent-network gen-types

up:
	docker compose up -d --wait

down:
	docker compose down

check:
	uv run --all-packages ruff check .
	uv run --all-packages ruff format --check .
	uv run --all-packages mypy --strict
	uv run --all-packages pytest

	corepack pnpm --filter @agentbench/web check-tokens
	corepack pnpm --filter @agentbench/web test
	corepack pnpm --filter @agentbench/web build
	API_KEY="$${API_KEY:-agentbench-test-key}" corepack pnpm --filter @agentbench/web test:security

gen-types:
	corepack pnpm --filter @agentbench/web gen-types

test:
	uv run --all-packages pytest

fmt:
	uv run --all-packages ruff check --fix .
	uv run --all-packages ruff format .

sandbox-image:
	docker build --target sandbox -f infra/docker/sandbox.Dockerfile -t agentbench/sandbox:py312 .

qa-tasks:
	docker compose --profile qa run --rm --build qa-runner

migrate:
	uv run --package agentbench-api alembic upgrade head

check-agent-network:
	docker compose --profile network-check run --rm --build plain-coder-network-check
