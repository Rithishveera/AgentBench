"""Serve a plain async handler as an AgentBench agent."""

from __future__ import annotations

import os

import uvicorn

from agentbench_sdk.server import Handler, create_app


def serve(fn: Handler) -> None:
    secret = os.environ.get("AGENT_SECRET")
    if not secret:
        raise RuntimeError("AGENT_SECRET must be set")
    uvicorn.run(create_app(fn, secret), host="0.0.0.0", port=8000)
