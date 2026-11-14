"""FastAPI server implementing the AgentBench external-agent contract."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from collections.abc import Awaitable, Callable

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from agentbench_sdk.context import RunContext
from agentbench_sdk.schemas import (
    MAX_REQUEST_BYTES,
    CompleteRequest,
    RunRequest,
    RunResult,
)
from agentbench_sdk.step_pusher import StepPusher

Handler = Callable[[RunContext], Awaitable[RunResult]]


def _signature(secret: str | bytes, timestamp: str, body: bytes) -> str:
    key = secret.encode() if isinstance(secret, str) else secret
    return hmac.new(key, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def _authenticated(
    secret: str | bytes, timestamp: str, body: bytes, signature: str
) -> bool:
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - sent_at) > 300:
        return False
    return hmac.compare_digest(_signature(secret, timestamp, body), signature)


def create_app(
    handler: Handler,
    secret: str | bytes,
    max_concurrency: int = 4,
) -> FastAPI:
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be positive")
    app = FastAPI()
    app.state.callback_transport = None
    app.state.llm_transport = None
    app.state.active = 0
    app.state.seen_run_ids = set()
    app.state.run_lock = asyncio.Lock()
    app.state.background_tasks = set()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/runs", status_code=202)
    async def start_run(request: Request) -> Response:
        body_buffer = bytearray()
        async for chunk in request.stream():
            if len(body_buffer) + len(chunk) > MAX_REQUEST_BYTES:
                return JSONResponse(
                    {"detail": "request body exceeds 2 MB"}, status_code=413
                )
            body_buffer.extend(chunk)
        body = bytes(body_buffer)
        timestamp = request.headers.get("X-AB-Timestamp", "")
        signature = request.headers.get("X-AB-Signature", "")
        if not _authenticated(secret, timestamp, body, signature):
            return JSONResponse(
                {"detail": "invalid request signature"}, status_code=401
            )
        try:
            run_request = RunRequest.model_validate_json(body)
        except Exception:
            return JSONResponse({"detail": "invalid run request"}, status_code=422)

        async with app.state.run_lock:
            if run_request.run_id in app.state.seen_run_ids:
                return JSONResponse(
                    {"detail": "run_id has already been used"}, status_code=409
                )
            if app.state.active >= max_concurrency:
                return JSONResponse({"detail": "agent is at capacity"}, status_code=503)
            app.state.seen_run_ids.add(run_request.run_id)
            app.state.active += 1

        task = asyncio.create_task(_execute(app, handler, run_request))
        app.state.background_tasks.add(task)
        task.add_done_callback(app.state.background_tasks.discard)
        return Response(status_code=202)

    return app


async def _execute(app: FastAPI, handler: Handler, run_request: RunRequest) -> None:
    pusher = StepPusher(
        run_request.callback,
        run_request.task.limits.max_steps,
        transport=app.state.callback_transport,
        redacted_secrets=(
            run_request.callback.token,
            *([run_request.llm.api_key] if run_request.llm is not None else []),
        ),
    )
    context = RunContext(
        run_request.task,
        run_request.llm,
        pusher,
        llm_transport=app.state.llm_transport,
    )
    completion = CompleteRequest(status="error", error="handler did not complete")
    try:
        result = await asyncio.wait_for(
            handler(context), timeout=run_request.task.limits.timeout_s
        )
        if not isinstance(result, RunResult):
            raise TypeError("handler must return RunResult")
        completion = CompleteRequest(
            status="success", patch=result.patch, answer=result.answer
        )
    except TimeoutError:
        completion = CompleteRequest(status="error", error="handler timed out")
    except Exception as error:
        completion = CompleteRequest(
            status="error", error=f"handler failed: {type(error).__name__}"
        )
    finally:
        try:
            await context.close()
        except Exception:
            pass
        try:
            completion.steps_dropped = await pusher.close()
        except Exception:
            completion.steps_dropped = pusher.steps_dropped
        try:
            await _post_completion(app, run_request, completion)
        except Exception:
            pass
        finally:
            async with app.state.run_lock:
                app.state.active -= 1


async def _post_completion(
    app: FastAPI,
    run_request: RunRequest,
    completion: CompleteRequest,
) -> None:
    url = str(run_request.callback.base_url).rstrip("/") + "/complete"
    try:
        async with httpx.AsyncClient(
            transport=app.state.callback_transport,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=1.0, read=2.0, write=2.0, pool=1.0),
        ) as client:
            await client.post(
                url,
                headers={"Authorization": f"Bearer {run_request.callback.token}"},
                json=completion.model_dump(mode="json", exclude_none=True),
            )
    except Exception:
        return
