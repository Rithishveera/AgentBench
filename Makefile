.PHONY: up down check test fmt sandbox-image qa-tasks

up:
	docker compose up -d --wait

down:
	docker compose down

check:
	uv run --all-packages ruff check .
	uv run --all-packages ruff format --check .
	uv run --all-packages mypy --strict
	uv run --all-packages pytest

test:
	uv run --all-packages pytest

fmt:
	uv run --all-packages ruff check --fix .
	uv run --all-packages ruff format .

sandbox-image:
	docker build --target sandbox -f infra/docker/sandbox.Dockerfile -t agentbench/sandbox:py312 .

qa-tasks:
	docker compose --profile qa run --rm --build qa-runner