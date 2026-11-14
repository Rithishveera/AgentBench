"""Structured JSON logging with recursive secret redaction."""

from __future__ import annotations

import re
from typing import Any, cast

import structlog
from structlog.typing import EventDict

_SENSITIVE_KEY = re.compile(r"password|secret|token|api[_-]?key|authorization", re.I)
_SECRET_VALUE = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
_REDACTED = "[REDACTED]"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _REDACTED if _SENSITIVE_KEY.search(str(key)) else _redact(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub(_REDACTED, value)
    return value


def redact_sensitive_data(
    logger: Any,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Redact secret-like keys and LiteLLM-style keys throughout an event."""
    del logger, method_name
    return cast(EventDict, _redact(event_dict))


def configure_logging() -> None:
    """Configure structlog to emit redacted JSON events."""
    structlog.configure(
        processors=[
            redact_sensitive_data,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
