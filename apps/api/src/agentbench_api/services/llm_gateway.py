"""Server-side integration with LiteLLM virtual keys and spend logs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentbench_api.config import Settings
from agentbench_api.db import get_session_factory
from agentbench_api.models import Run


class LiteLLMGatewayError(RuntimeError):
    """Raised when LiteLLM cannot perform a management operation."""


def _base_url(settings: Settings) -> str:
    return settings.litellm_url.rstrip("/")


def _master_key(settings: Settings) -> str:
    if settings.litellm_master_key is None:
        raise LiteLLMGatewayError("LITELLM_MASTER_KEY is not configured")
    return settings.litellm_master_key.get_secret_value()


def _duration(ttl: int | timedelta) -> str:
    seconds = int(ttl.total_seconds()) if isinstance(ttl, timedelta) else ttl
    if seconds < 1:
        raise ValueError("ttl must be at least one second")
    return f"{seconds}s"


async def mint_run_key(
    run_id: UUID | str,
    allowed_models: list[str],
    *,
    max_budget_usd: float,
    ttl: int | timedelta,
    settings: Settings | None = None,
) -> str:
    """Create a model-scoped LiteLLM key with a per-run spend cap and lifetime."""
    if not allowed_models or any(not model.strip() for model in allowed_models):
        raise ValueError("allowed_models must contain at least one model")
    if max_budget_usd <= 0:
        raise ValueError("max_budget_usd must be positive")
    app_settings = settings or Settings()
    run_alias = str(run_id)
    payload = {
        "models": list(dict.fromkeys(allowed_models)),
        "max_budget": max_budget_usd,
        "duration": _duration(ttl),
        "key_alias": run_alias,
        "metadata": {"run_id": run_alias},
        "allowed_routes": ["llm_api_routes"],
    }
    headers = {"Authorization": f"Bearer {_master_key(app_settings)}"}
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(10.0),
    ) as client:
        response = await client.post(
            f"{_base_url(app_settings)}/key/generate",
            headers=headers,
            json=payload,
        )
    if not response.is_success:
        raise LiteLLMGatewayError(
            f"LiteLLM key generation failed (HTTP {response.status_code})"
        )
    response_data: Any = response.json()
    key = response_data.get("key") if isinstance(response_data, dict) else None
    if not isinstance(key, str) or not key:
        raise LiteLLMGatewayError("LiteLLM key generation returned no key")
    return key


async def revoke_key(
    key: str,
    *,
    settings: Settings | None = None,
) -> None:
    """Revoke a previously generated LiteLLM virtual key."""
    app_settings = settings or Settings()
    headers = {"Authorization": f"Bearer {_master_key(app_settings)}"}
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(10.0),
    ) as client:
        response = await client.post(
            f"{_base_url(app_settings)}/key/delete",
            headers=headers,
            json={"keys": [key]},
        )
    if not response.is_success:
        raise LiteLLMGatewayError(
            f"LiteLLM key revocation failed (HTTP {response.status_code})"
        )


@asynccontextmanager
async def managed_run_key(
    run_id: UUID | str,
    allowed_models: list[str],
    *,
    max_budget_usd: float,
    ttl: int | timedelta,
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    """Revoke a minted virtual key when the run's managed scope exits."""
    key = await mint_run_key(
        run_id,
        allowed_models,
        max_budget_usd=max_budget_usd,
        ttl=ttl,
        settings=settings,
    )
    try:
        yield key
    finally:
        await revoke_key(key, settings=settings)


def _aggregate_logs(logs: list[dict[str, Any]]) -> dict[str, int | float]:
    return {
        "tokens_in": sum(
            int(log.get("prompt_tokens") or log.get("input_tokens") or 0)
            for log in logs
        ),
        "tokens_out": sum(
            int(log.get("completion_tokens") or log.get("output_tokens") or 0)
            for log in logs
        ),
        "cost_usd": sum(float(log.get("spend") or 0.0) for log in logs),
        "calls": len(logs),
    }


async def get_run_usage(
    run_id: UUID,
    *,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, int | float]:
    """Read paginated LiteLLM spend logs for a run's hashed virtual key."""
    factory = session_factory or get_session_factory()
    async with factory() as session:
        run = await session.get(Run, run_id)
        if run is None or run.litellm_key_hash is None or run.started_at is None:
            return _aggregate_logs([])
        key_hash = run.litellm_key_hash
        start_at = run.started_at - timedelta(seconds=1)
        end_at = (run.finished_at or datetime.now(UTC)) + timedelta(seconds=1)

    app_settings = settings or Settings()
    headers = {"Authorization": f"Bearer {_master_key(app_settings)}"}
    query: dict[str, str | int] = {
        "api_key": key_hash,
        "start_date": start_at.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end_at.strftime("%Y-%m-%d %H:%M:%S"),
        "page_size": 1000,
    }
    logs: list[dict[str, Any]] = []
    page = 1
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(10.0),
    ) as client:
        while True:
            response = await client.get(
                f"{_base_url(app_settings)}/spend/logs/v2",
                headers=headers,
                params={**query, "page": page},
            )
            if not response.is_success:
                raise LiteLLMGatewayError(
                    f"LiteLLM spend-log lookup failed (HTTP {response.status_code})"
                )
            response_data: Any = response.json()
            if not isinstance(response_data, dict):
                raise LiteLLMGatewayError("LiteLLM returned invalid spend logs")
            page_logs = response_data.get("data")
            if not isinstance(page_logs, list):
                raise LiteLLMGatewayError("LiteLLM returned invalid spend logs")
            logs.extend(row for row in page_logs if isinstance(row, dict))
            total_pages = int(response_data.get("total_pages", page))
            if not page_logs or page >= total_pages:
                break
            page += 1
    return _aggregate_logs(logs)
