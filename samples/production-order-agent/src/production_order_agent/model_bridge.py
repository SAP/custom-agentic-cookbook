"""Private OpenAI-compatible bridge to the approved custom-model OAuth adapter."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from production_order_agent.custom_model import summarize_with_custom_model

MAX_BODY_BYTES = 128 * 1024
MAX_RECORD_BYTES = 64 * 1024
MAX_ASSISTANT_BYTES = 16 * 1024
BODY_TIMEOUT_SECONDS = 10
UPSTREAM_TIMEOUT_SECONDS = 300
Summarizer = Callable[[str, str, list[dict[str, Any]], list[dict[str, Any]]], Awaitable[str]]


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": message, "type": "gateway_error"}},
        status_code=status,
        headers={"Connection": "close", "Cache-Control": "no-store"},
    )


def _business_input(payload: Any, model: str):
    if not isinstance(payload, dict) or payload.get("model") != model:
        raise ValueError
    maximum = payload.get("max_tokens", 2048)
    if type(maximum) is not int or not 1 <= maximum <= 2048:
        raise ValueError
    if payload.get("stream", False) is not False:
        raise ValueError
    messages = payload.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 8:
        raise ValueError
    if any(not isinstance(message, dict) for message in messages):
        raise ValueError
    users = [message for message in messages if message.get("role") == "user"]
    if len(users) != 1 or not isinstance(users[0].get("content"), str):
        raise ValueError
    content = users[0]["content"]
    if len(content.encode()) > MAX_RECORD_BYTES:
        raise OverflowError
    records = json.loads(content)
    if not isinstance(records, dict):
        raise ValueError
    order = records.get("manufacturing_order")
    if not isinstance(order, str) or not re.fullmatch(r"[0-9]{1,20}", order):
        raise ValueError
    statuses, operations = records.get("statuses"), records.get("operations")
    for rows in (statuses, operations):
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError
        if len(rows) > 200:
            raise OverflowError
    return order, statuses, operations


def create_app(*, summarizer: Summarizer = summarize_with_custom_model) -> Starlette:
    model = os.getenv("MODEL_NAME", "").strip()
    token = os.getenv("MODEL_GATEWAY_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", model):
        raise RuntimeError("The bridge requires an approved MODEL_NAME")
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{16,256}", token):
        raise RuntimeError("The bridge requires a valid MODEL_GATEWAY_TOKEN")
    expected = ("Bearer " + token).encode()

    async def health(request: Request):
        return JSONResponse({"ready": True}, headers={"Cache-Control": "no-store"})

    async def completions(request: Request):
        auth = request.headers.getlist("authorization")
        if len(auth) != 1 or not hmac.compare_digest(auth[0].encode(), expected):
            return _error(401, "Unauthorized")
        if request.headers.get("content-encoding", "identity").lower() != "identity":
            return _error(400, "Invalid request")
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            return _error(400, "Invalid request")
        try:
            lengths = request.headers.getlist("content-length")
            if len(lengths) > 1:
                raise ValueError
            if lengths and (not lengths[0].isdigit() or int(lengths[0]) > MAX_BODY_BYTES):
                return _error(413, "Request limit exceeded")
            body = bytearray()
            async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        return _error(413, "Request limit exceeded")
                    body.extend(chunk)
            order, statuses, operations = _business_input(json.loads(body), model)
        except OverflowError:
            return _error(413, "Request limit exceeded")
        except TimeoutError:
            return _error(408, "Request timed out")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return _error(400, "Invalid request")
        except Exception:
            return _error(400, "Invalid request")
        try:
            async with asyncio.timeout(UPSTREAM_TIMEOUT_SECONDS):
                content = await summarizer(model, order, statuses, operations)
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            if len(content.encode()) > MAX_ASSISTANT_BYTES:
                raise ValueError
        except TimeoutError:
            return _error(504, "Upstream timed out")
        except Exception:
            return _error(502, "Upstream unavailable")
        return JSONResponse(
            {
                "id": "chatcmpl-" + uuid.uuid4().hex,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            },
            headers={"Connection": "close", "Cache-Control": "no-store"},
        )

    return Starlette(
        routes=[
            Route("/healthz", health, methods=["GET"]),
            Route("/v1/chat/completions", completions, methods=["POST"]),
        ]
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        create_app(),
        host=os.getenv("MODEL_GATEWAY_HOST", "127.0.0.1"),
        port=int(os.getenv("MODEL_GATEWAY_PORT", "8081")),
        access_log=False,
        log_level="warning",
    )
