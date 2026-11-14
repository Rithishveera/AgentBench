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
    litellm_master_key: SecretStr | None = Field(
        default=None,
        validation_alias="LITELLM_MASTER_KEY",
    )
    litellm_url: str = Field(
        default="http://litellm:4000",
        min_length=1,
        validation_alias="LITELLM_URL",
    )
    litellm_model: str = Field(
        default="agentbench-default",
        min_length=1,
        validation_alias="LITELLM_MODEL",
    )
    agent_callback_base_url: str = Field(
        default="http://agent-ingress:8080/internal",
        min_length=1,
        validation_alias="AGENT_CALLBACK_BASE_URL",
    )
    db_pool_size: int = Field(default=5, ge=1, le=50, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(
        default=10, ge=0, le=50, validation_alias="DB_MAX_OVERFLOW"
    )
    allowed_agent_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias="ALLOWED_AGENT_HOSTS",
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias="CORS_ORIGINS",
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [
                origin.strip().rstrip("/")
                for origin in value.split(",")
                if origin.strip()
            ]
        if isinstance(value, list) and all(isinstance(origin, str) for origin in value):
            return [origin.rstrip("/") for origin in value]
        raise ValueError("CORS_ORIGINS must be a comma-separated string or list")
