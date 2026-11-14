"""Agent URL validation and DNS-pinned HTTP transport."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True, slots=True)
class PinnedAddress:
    scheme: str
    hostname: str
    port: int
    address: str
    allowlisted: bool

    @property
    def host_header(self) -> str:
        host = f"[{self.hostname}]" if ":" in self.hostname else self.hostname
        default_port = 443 if self.scheme == "https" else 80
        return host if self.port == default_port else f"{host}:{self.port}"


def _allowed(hostname: str, allowed_hosts: tuple[str, ...]) -> bool:
    normalized = hostname.rstrip(".").casefold()
    return normalized in {host.rstrip(".").casefold() for host in allowed_hosts}


def _resolve(hostname: str, port: int) -> list[str]:
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise ValueError(f"agent hostname cannot be resolved: {hostname}") from error
    addresses = sorted({str(record[4][0]) for record in records})
    if not addresses:
        raise ValueError(f"agent hostname has no addresses: {hostname}")
    return addresses


def validate_agent_url(
    url: str,
    allowed_hosts: tuple[str, ...] | list[str] = (),
) -> PinnedAddress:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("agent URL must be an absolute HTTP or HTTPS URL")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ValueError("agent URL cannot contain credentials or a fragment")
    hostname = parsed.hostname.rstrip(".").casefold()
    allowlisted = _allowed(hostname, tuple(allowed_hosts))
    if parsed.scheme != "https" and not allowlisted:
        raise ValueError("HTTPS is required unless the agent host is allowlisted")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        addresses = _resolve(hostname, port)
    else:
        addresses = [literal.compressed]

    parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
    if not allowlisted and any(not address.is_global for address in parsed_addresses):
        raise ValueError("agent host resolves to a private, loopback, or reserved address")
    return PinnedAddress(
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        address=parsed_addresses[0].compressed,
        allowlisted=allowlisted,
    )


class PinnedIPTransport(httpx.AsyncHTTPTransport):
    def __init__(self, pinned: PinnedAddress) -> None:
        super().__init__(verify=True, retries=0)
        self._pinned = pinned

    def _pin_request(self, request: httpx.Request) -> httpx.Request:
        request_port = request.url.port or (443 if request.url.scheme == "https" else 80)
        if (
            request.url.scheme != self._pinned.scheme
            or request.url.host.rstrip(".").casefold() != self._pinned.hostname
            or request_port != self._pinned.port
        ):
            raise httpx.RequestError(
                "pinned transport cannot access another origin", request=request
            )
        headers = request.headers.copy()
        headers["host"] = self._pinned.host_header
        extensions = dict(request.extensions)
        if self._pinned.scheme == "https":
            extensions["sni_hostname"] = self._pinned.hostname.encode("ascii")
        return httpx.Request(
            method=request.method,
            url=request.url.copy_with(host=self._pinned.address),
            headers=headers,
            content=request.stream,
            extensions=extensions,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await super().handle_async_request(self._pin_request(request))


def create_pinned_transport(pinned: PinnedAddress) -> PinnedIPTransport:
    return PinnedIPTransport(pinned)
