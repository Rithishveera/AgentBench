from __future__ import annotations

import os
import socket
from urllib.error import HTTPError
from urllib.request import urlopen


def _must_be_unreachable(host: str, port: int) -> None:
    try:
        connection = socket.create_connection((host, port), timeout=2)
    except OSError:
        return
    connection.close()
    raise RuntimeError(f"unexpected connection to {host}:{port}")


def _must_return_200(url: str) -> None:
    with urlopen(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")


def _must_be_forbidden(url: str) -> None:
    try:
        with urlopen(url, timeout=5) as response:
            raise RuntimeError(f"unexpected HTTP {response.status} for {url}")
    except HTTPError as error:
        if error.code != 403:
            raise RuntimeError(
                f"{url} returned HTTP {error.code}, expected 403"
            ) from error


def main() -> None:
    _must_be_unreachable("postgres", 5432)
    _must_be_unreachable("redis", 6379)
    _must_return_200(os.environ["LITELLM_HEALTH_URL"])
    _must_return_200(os.environ["INTERNAL_HEALTH_URL"])
    _must_return_200(os.environ["AGENT_HEALTH_URL"])
    _must_be_forbidden("http://agent-ingress:8080/agents")
    print("agent network boundaries passed")


if __name__ == "__main__":
    main()
