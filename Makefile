.PHONY: up down check test fmt

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