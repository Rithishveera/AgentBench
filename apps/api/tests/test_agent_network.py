from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from agentbench_api.config import Settings
from agentbench_api.main import create_app
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]


def test_compose_keeps_agent_network_separate() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]

    assert set(services["plain-coder"]["networks"]) == {"agents_net"}
    assert set(services["plain-coder-network-check"]["networks"]) == {"agents_net"}
    assert set(services["postgres"]["networks"]) == {"platform_net"}
    assert set(services["redis"]["networks"]) == {"platform_net"}
    assert set(services["api"]["networks"]) == {"platform_net"}
    assert set(services["worker"]["networks"]) == {"platform_net", "agents_net"}
    assert set(services["litellm"]["networks"]) == {"platform_net", "agents_net"}
    assert set(services["agent-ingress"]["networks"]) == {
        "platform_net",
        "agents_net",
    }
    assert "ports" not in services["litellm"]
    assert "DOCKER_HOST" not in services["api"]["environment"]
    assert "LITELLM_MASTER_KEY" in services["worker"]["environment"]
    assert "OPENAI_API_KEY" not in services["plain-coder"]["environment"]
    assert "LITELLM_MASTER_KEY" not in services["plain-coder"]["environment"]
    assert services["litellm"]["environment"]["DISABLE_ADMIN_UI"] == "true"
    assert services["litellm"]["environment"]["LITELLM_TELEMETRY_DISABLED"] == "true"


def test_litellm_config_reads_credentials_only_from_environment() -> None:
    config = yaml.safe_load((ROOT / "infra/litellm/config.yaml").read_text())
    model = config["model_list"][0]

    assert model["model_name"] == "os.environ/LITELLM_MODEL"
    assert model["litellm_params"]["model"] == "os.environ/LITELLM_UPSTREAM_MODEL"
    assert model["litellm_params"]["api_key"] == "os.environ/OPENAI_API_KEY"
    assert config["general_settings"]["master_key"] == "os.environ/LITELLM_MASTER_KEY"
    assert config["litellm_settings"]["global_disable_no_log_param"] is True


def test_agent_ingress_forwards_only_internal_and_health() -> None:
    ingress = (ROOT / "infra/nginx/agents.conf").read_text()

    assert "location = /health" in ingress
    assert "location ^~ /internal/" in ingress
    assert "location / {" in ingress
    assert "return 403" in ingress


@asynccontextmanager
async def _noop_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


def test_internal_and_public_health_routes_are_available() -> None:
    settings = Settings(
        API_KEY="api-key",
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        DATABASE_URL="postgresql+asyncpg://agentbench:pw@localhost/agentbench",
        REDIS_URL="redis://:pw@localhost:6379/0",
        _env_file=None,
    )
    app = create_app(settings)
    app.router.lifespan_context = _noop_lifespan

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/internal/health").status_code == 200
