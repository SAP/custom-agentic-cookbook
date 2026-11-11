"""Summarize fetched records through an approved OpenAI-compatible gateway."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import re
from contextlib import suppress
from datetime import date
from typing import Any
from urllib.parse import urlsplit

import httpx

MAX_RESPONSE_BYTES = 128 * 1024
MAX_ASSISTANT_BYTES = 16 * 1024
REQUEST_TIMEOUT_SECONDS = 30


def _gateway_url(value: str) -> str:
    url = value.strip()
    if (
        not url
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127 for character in url
        )
        or "\\" in url
    ):
        raise RuntimeError("MODEL_GATEWAY_URL must be a valid gateway base URL")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError:
        raise RuntimeError("MODEL_GATEWAY_URL must be a valid gateway base URL") from None
    if (
        not hostname
        or parsed.username is not None
        or parsed.password is not None
        or "?" in url
        or "#" in url
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise RuntimeError("MODEL_GATEWAY_URL must omit user information, query, and fragment")
    local = hostname == "localhost"
    if not local:
        with suppress(ValueError):
            local = ipaddress.ip_address(hostname).is_loopback
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise RuntimeError("MODEL_GATEWAY_URL requires HTTPS or local loopback HTTP")
    return url.rstrip("/") + "/chat/completions"


async def summarize_with_gateway(
    model_name: str,
    manufacturing_order: str,
    statuses: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Return one assistant text reply without exposing gateway diagnostics."""

    model = model_name.strip()
    if not model:
        raise RuntimeError("MODEL_NAME is required when LLM_PROVIDER=openai-compatible")
    url = _gateway_url(os.getenv("MODEL_GATEWAY_URL", ""))
    api_key = os.getenv("MODEL_GATEWAY_API_KEY", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", api_key):
        raise RuntimeError("MODEL_GATEWAY_API_KEY must contain a valid bearer token")

    records = json.dumps(
        {
            "today": date.today().isoformat(),
            "manufacturing_order": manufacturing_order,
            "statuses": statuses,
            "operations": operations,
        },
        default=str,
    )
    if len(statuses) > 200 or len(operations) > 200 or len(records.encode()) > 65536:
        raise RuntimeError("Gateway input exceeds the business record bound")

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        async with (
            asyncio.timeout(REQUEST_TIMEOUT_SECONDS),
            httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
                transport=transport,
            ) as client,
            client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
                json={
                    "model": model,
                    "temperature": 0,
                    "stream": False,
                    "max_tokens": 2048,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a production-planning assistant. Summarize only the "
                                "supplied SAP S/4HANA records. Use Status, Scheduled operations, "
                                "and Delay assessment sections. Treat an operation as a potential "
                                "delay only when its scheduled end date is before today's date "
                                "and it is not finally confirmed. State when the records are "
                                "insufficient; never invent causes or dates."
                            ),
                        },
                        {
                            "role": "user",
                            "content": records,
                        },
                    ],
                },
            ) as response,
        ):
            response.raise_for_status()
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise RuntimeError("Gateway returned an unsupported response encoding")
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise RuntimeError("Gateway response exceeds the byte bound")
                body.extend(chunk)
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Gateway request failed with HTTP {exc.response.status_code}") from None
    except (httpx.RequestError, TimeoutError):
        raise RuntimeError("Gateway request failed") from None
    try:
        payload = json.loads(body)
    except ValueError:
        raise RuntimeError("Gateway returned invalid JSON") from None
    try:
        message = payload["choices"][0]["message"]
        content = message["content"]
        if (
            message.get("role") != "assistant"
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        raise RuntimeError("Gateway returned no usable assistant reply") from None
    if len(content.encode("utf-8")) > MAX_ASSISTANT_BYTES:
        raise RuntimeError("Gateway assistant reply exceeds the byte bound")
    return content.strip()
