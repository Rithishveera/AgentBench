"""
Load test: 200 concurrent WebSocket clients on one benchmark.

Usage:
    python apps/api/scripts/load_test_ws.py \
        --api-url http://localhost:8000 \
        --api-key <key> \
        --benchmark-id <uuid> \
        --clients 200

Reports: connection time, peak RSS memory on the API process (if psutil available),
messages received per client.  Run against a live API + Redis instance.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from typing import Any

try:
    import websockets
    import websockets.exceptions
except ImportError:
    raise SystemExit("pip install websockets") from None


async def _get_ticket(session: Any, api_url: str, api_key: str, bid: str) -> str | None:
    import aiohttp

    async with aiohttp.ClientSession() as http:
        async with http.post(
            f"{api_url}/benchmarks/{bid}/stream-ticket",
            headers={"X-API-Key": api_key},
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("ticket")


async def _client(
    api_url: str,
    api_key: str,
    bid: str,
    results: list[dict[str, Any]],
    idx: int,
) -> None:
    start = time.perf_counter()
    try:
        import aiohttp

        async with aiohttp.ClientSession() as http:
            async with http.post(
                f"{api_url}/benchmarks/{bid}/stream-ticket",
                headers={"X-API-Key": api_key},
            ) as resp:
                if resp.status != 200:
                    results.append({"idx": idx, "error": f"ticket HTTP {resp.status}"})
                    return
                data = await resp.json()
                ticket = data.get("ticket")

        ws_url = api_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/benchmarks/{bid}/stream?ticket={ticket}"

        msgs = 0
        async with websockets.connect(ws_url) as ws:  # type: ignore[attr-defined]
            connect_ms = (time.perf_counter() - start) * 1000
            # Read up to 5 messages then close (non-blocking drain).
            try:
                async for _msg in ws:
                    msgs += 1
                    if msgs >= 5:
                        break
            except websockets.exceptions.ConnectionClosed:
                pass
        results.append(
            {"idx": idx, "connect_ms": connect_ms, "msgs": msgs, "error": None}
        )
    except Exception as exc:
        results.append({"idx": idx, "error": str(exc), "connect_ms": None, "msgs": 0})


async def run(api_url: str, api_key: str, bid: str, n: int) -> None:
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        raise SystemExit("pip install aiohttp websockets") from None

    results: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    await asyncio.gather(
        *[_client(api_url, api_key, bid, results, i) for i in range(n)]
    )
    elapsed = time.perf_counter() - t0

    errors = [r for r in results if r.get("error")]
    ok = [r for r in results if not r.get("error")]
    connect_times = [r["connect_ms"] for r in ok if r.get("connect_ms") is not None]

    print(f"\n=== Load test: {n} clients on benchmark {bid} ===")
    print(f"Total wall time: {elapsed:.2f}s")
    print(f"Successful connections: {len(ok)} / {n}")
    print(f"Errors: {len(errors)}")
    if errors:
        from collections import Counter

        counts = Counter(r["error"] for r in errors)
        for msg, cnt in counts.most_common(5):
            print(f"  {cnt}x  {msg}")
    if connect_times:
        p95_idx = int(len(connect_times) * 0.95)
        print(f"Connect time p50: {statistics.median(connect_times):.1f} ms")
        print(f"Connect time p95: {sorted(connect_times)[p95_idx]:.1f} ms")
        print(f"Connect time max: {max(connect_times):.1f} ms")

    try:
        import os

        import psutil

        proc = psutil.Process(os.getpid())
        rss_mb = proc.memory_info().rss / 1024 / 1024
        print(f"Client-process RSS: {rss_mb:.1f} MB")
    except ImportError:
        print("(install psutil for memory stats)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WS load test")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument("--clients", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(run(args.api_url, args.api_key, args.benchmark_id, args.clients))
