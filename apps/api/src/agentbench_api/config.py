"""Application settings loaded from environment variables or a local .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_SECRET_ENV_NAMES = {
    "api_key": "API_KEY",
    "encryption_key": "ENCRYPTION_KEY",
    "database_url": "DATABASE_URL",
    "redis_url": "REDIS_URL",
}


class Settings(BaseSettings):
    """Required secrets and optional paths/host allowlist for the API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    api_key: SecretStr = Field(validation_alias="API_KEY")
    encryption_key: SecretStr = Field(validation_alias="ENCRYPTION_KEY")
    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    redis_url: SecretStr = Field(validation_alias="REDIS_URL")
    allowed_agent_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias="ALLOWED_AGENT_HOSTS",
    )
    suites_dir: Path = Field(default=Path("suites"), validation_alias="SUITES_DIR")

    def __init__(self, **values: Any) -> None:
        try:
            super().__init__(**values)
        except ValidationError as exc:
            locations = {
                str(location).casefold()
                for error in exc.errors()
                if error["type"] == "missing"
                for location in error["loc"]
            }
            missing = [
                env_name
                for field_name, env_name in _SECRET_ENV_NAMES.items()
                if field_name.casefold() in locations
                or env_name.casefold() in locations
            ]
            if missing:
                raise ValueError(
                    "Missing required environment variables: " + ", ".join(missing)
                ) from None
            raise

    @field_validator("allowed_agent_hosts", mode="before")
    @classmethod
    def parse_allowed_agent_hosts(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [host.strip() for host in value.split(",") if host.strip()]
        if isinstance(value, list) and all(isinstance(host, str) for host in value):
            return value
        raise ValueError("ALLOWED_AGENT_HOSTS must be a comma-separated string or list")
