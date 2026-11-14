from __future__ import annotations

import socket

import httpx
import pytest

from agentbench_api.security.ssrf import (
    PinnedAddress,
    create_pinned_transport,
    validate_agent_url,
)


def _private_resolution(host: str, port: int, *, type: int) -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port))]


@pytest.mark.parametrize(
    "url",
    [
        "https://169.254.169.254/latest/meta-data/",
        "https://localhost/",
        "https://127.0.0.1/",
        "https://192.168.1.12/",
        "https://10.0.0.4/",
    ],
)
def test_private_loopback_and_metadata_addresses_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        validate_agent_url(url)


def test_dns_resolution_to_private_ip_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _private_resolution)
    with pytest.raises(ValueError, match="resolves to a private"):
        validate_agent_url("https://agent.example")


def test_allowlisted_development_host_may_use_http_and_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _private_resolution)
    pinned = validate_agent_url("http://agent.dev:8080", ["agent.dev"])
    assert pinned.address == "10.1.2.3"
    assert pinned.allowlisted is True


def test_allowlist_is_exact_hostname_match() -> None:
    with pytest.raises(ValueError, match="HTTPS is required"):
        validate_agent_url("http://sub.agent.dev", ["agent.dev"])


def test_pinned_transport_rewrites_destination_and_preserves_host_sni() -> None:
    pinned = PinnedAddress("https", "agent.example", 443, "203.0.113.7", False)
    transport = create_pinned_transport(pinned)
    request = httpx.Request("GET", "https://agent.example/health")
    rewritten = transport._pin_request(request)
    assert rewritten.url.host == "203.0.113.7"
    assert rewritten.headers["host"] == "agent.example"
    assert rewritten.extensions["sni_hostname"] == b"agent.example"


def test_pinned_transport_rejects_another_origin() -> None:
    transport = create_pinned_transport(
        PinnedAddress("https", "agent.example", 443, "203.0.113.7", False)
    )
    with pytest.raises(httpx.RequestError, match="another origin"):
        transport._pin_request(httpx.Request("GET", "https://other.example/health"))
