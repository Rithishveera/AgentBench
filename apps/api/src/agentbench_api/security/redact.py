"""Redaction and size limits for untrusted callback payloads."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

MAX_STEP_PAYLOAD_BYTES = 64 * 1024
_SECRET_VALUE = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
_SENSITIVE_KEY = re.compile(r"password|secret|token|api[_-]?key|authorization", re.I)
_TOKEN_COUNTS = {
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "input_tokens",
    "output_tokens",
}


def _redact(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if _SENSITIVE_KEY.search(str(key))
            and not (str(key) in _TOKEN_COUNTS and type(nested) is int)
            else _redact(nested, secrets)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        result = _SECRET_VALUE.sub("[REDACTED]", value)
        for secret in secrets:
            if secret:
                result = result.replace(secret, "[REDACTED]")
        return result
    return value


def redact_payload(
    obj: Any,
    secrets: Iterable[str] = (),
) -> tuple[dict[str, Any], bool]:
    sanitized = _redact(obj, tuple(secrets))
    if not isinstance(sanitized, dict):
        sanitized = {"value": sanitized}
    encoded = json.dumps(
        sanitized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) <= MAX_STEP_PAYLOAD_BYTES:
        return sanitized, False
    preview = encoded[: MAX_STEP_PAYLOAD_BYTES // 4].decode("utf-8", errors="ignore")
    bounded = {"preview": preview}
    return bounded, True
