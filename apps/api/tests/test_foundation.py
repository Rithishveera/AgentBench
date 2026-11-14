from __future__ import annotations

import json

import pytest
import structlog
from agentbench_api.config import Settings
from agentbench_api.logging import configure_logging


def test_settings_error_lists_all_missing_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = ("API_KEY", "ENCRYPTION_KEY", "DATABASE_URL", "REDIS_URL")
    for name in names:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError) as exc_info:
        Settings(_env_file=None)

    message = str(exc_info.value)
    for name in names:
        assert name in message


def test_settings_parse_allowed_agent_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://:pass@localhost/0")
    monkeypatch.setenv("ALLOWED_AGENT_HOSTS", "agent.example,internal.example")

    settings = Settings(_env_file=None)

    assert settings.allowed_agent_hosts == ["agent.example", "internal.example"]


def test_json_logging_redacts_nested_secrets(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    token = "sk-" + "1234567890abcdefghijklmnop"
    structlog.get_logger().info(
        "agent event",
        payload={
            "nested": {
                "callback_token": "run-token",
                "message": f"key {token} is hidden",
            }
        },
    )

    output = capsys.readouterr().out
    event = json.loads(output)
    assert event["payload"]["nested"]["callback_token"] == "[REDACTED]"
    assert token not in output
    assert "[REDACTED]" in event["payload"]["nested"]["message"]
