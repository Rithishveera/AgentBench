from __future__ import annotations

import json

from agentbench_api.security.redact import MAX_STEP_PAYLOAD_BYTES, redact_payload


def test_redacts_sensitive_keys_nested_and_secret_patterns() -> None:
    payload, truncated = redact_payload(
        {
            "nested": {
                "Authorization": "Bearer hidden",
                "ordinary": "key sk-abcdefghijklmnopqrstuvwxyz is secret",
                "total_tokens": 9,
            }
        },
        secrets=("hidden",),
    )
    assert truncated is False
    assert payload["nested"]["Authorization"] == "[REDACTED]"
    assert "sk-abc" not in payload["nested"]["ordinary"]
    assert payload["nested"]["total_tokens"] == 9


def test_truncates_serialized_payload_to_cap() -> None:
    payload, truncated = redact_payload({"message": "x" * (MAX_STEP_PAYLOAD_BYTES * 2)})
    assert truncated is True
    assert len(json.dumps(payload, ensure_ascii=False).encode()) <= MAX_STEP_PAYLOAD_BYTES
