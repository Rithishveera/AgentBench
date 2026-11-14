"""FastAPI application factory and API lifecycle."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send
import structlog
import yaml

from agentbench_api.config import Settings
from agentbench_api.db import create_engine
from agentbench_api.repositories import upsert_tasks
from agentbench_api.routers.agents import router as agents_router
from agentbench_api.routers.internal import router as internal_router
from agentbench_api.routers.runs import router as runs_router
from agentbench_api.routers.suites import router as suites_router
from agentbench_tasks.loader import Suite, load_suite

MAX_REQUEST_BYTES = 2 * 1024 * 1024
logger = structlog.get_logger(__name__)


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content_length = next(
            (
                value
                for name, value in scope.get("headers", [])
                if name.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send)
                return

        messages: list[Message] = []
        body_size = 0
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            body_size += len(body)
            if body_size > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            messages.append(message)
            more_body = message.get("more_body", False)
        position = 0

        async def replay() -> Message:
            nonlocal position
            if position < len(messages):
                message = messages[position]
                position += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {
                "type": "about:blank",
                "title": "Request body too large",
                "status": 413,
                "detail": "Request body exceeds 2 MB",
            },
            status_code=413,
            media_type="application/problem+json",
        )
        await response(scope, receive, send)


def _suite_directories(root: Path) -> list[Path]:
    if (root / "suite.yaml").is_file():
        return [root]
    if not root.is_dir():
        return []
    return sorted(
        (
            path
            for path in root.iterdir()
            if path.is_dir() and (path / "suite.yaml").is_file()
        ),
        key=lambda path: path.name,
    )


def _public_suite_data(suite_dir: Path) -> dict[str, Any]:
    metadata = yaml.safe_load((suite_dir / "suite.yaml").read_text(encoding="utf-8"))
    title = metadata.get("title", suite_dir.name) if isinstance(metadata, dict) else suite_dir.name
    return {"id": suite_dir.name, "title": title}


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    redis_client: Redis | None = None,
) -> FastAPI:
    app_settings = settings or Settings()
    engine = None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal engine
        factory = session_factory
        if factory is None:
            engine = create_engine(app_settings)
            factory = async_sessionmaker(engine, expire_on_commit=False)
        app.state.session_factory = factory
        app.state.redis = redis_client or Redis.from_url(
            app_settings.redis_url.get_secret_value(), decode_responses=True
        )
        suites: dict[str, Suite] = {}
        try:
            for suite_dir in _suite_directories(app_settings.suites_dir):
                suite = load_suite(suite_dir)
                async with factory() as session:
                    await upsert_tasks(session, suite)
                    await session.commit()
                suites[suite_dir.name] = suite
            app.state.suites = suites
            yield
        finally:
            await app.state.redis.aclose()
            if engine is not None:
                await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.settings = app_settings
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_logging(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            {
                "type": "about:blank",
                "title": "Request failed",
                "status": error.status_code,
                "detail": str(error.detail),
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=error.status_code,
            headers=error.headers,
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del error
        return JSONResponse(
            {
                "type": "about:blank",
                "title": "Invalid request",
                "status": 422,
                "detail": "Request validation failed",
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=422,
            media_type="application/problem+json",
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.error(
            "request_failed",
            request_id=getattr(request.state, "request_id", None),
            error_type=type(error).__name__,
        )
        return JSONResponse(
            {
                "type": "about:blank",
                "title": "Internal server error",
                "status": 500,
                "detail": "The request could not be completed",
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=500,
            media_type="application/problem+json",
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(agents_router)
    app.include_router(suites_router)
    app.include_router(runs_router)
    app.include_router(internal_router, prefix="/internal")
    return app
