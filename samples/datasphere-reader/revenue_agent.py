"""Deterministic, bounded revenue consumer; no model or raw-query interface."""

import asyncio
import ipaddress
import json
import logging
import os
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation, localcontext
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client

LIMIT = 50
MCP_RECEIVE_BYTES = 65536
_MCP_LOG_SCOPE = ContextVar("revenue_mcp_log_scope", default=False)


class _SafeTransportLog(logging.Filter):
    def __init__(self, *, scoped=False):
        super().__init__()
        self.scoped = scoped

    def filter(self, record):
        if self.scoped and not _MCP_LOG_SCOPE.get():
            return True
        if record.levelno < logging.WARNING:
            return False
        record.msg = "MCP transport failed; check the approved configuration"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


_SAFE_TRANSPORT_LOG = _SafeTransportLog()
_SAFE_ROOT_LOG = _SafeTransportLog(scoped=True)


class _BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        received = 0
        async for chunk in self.stream:
            received += len(chunk)
            if received > MCP_RECEIVE_BYTES:
                raise ValueError("MCP response exceeded the receive limit")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class _BoundedTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)

    async def handle_async_request(self, request):
        response = await self.transport.handle_async_request(request)
        # Refuse compression before HTTPX can expand it into an unbounded buffer.
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            await response.aclose()
            raise ValueError("MCP compressed responses are not supported")
        response.stream = _BoundedStream(response.stream)
        return response

    async def aclose(self):
        await self.transport.aclose()


def bounded_mcp_client(**kwargs):
    headers = {**(kwargs.pop("headers", None) or {}), "Accept-Encoding": "identity"}
    return httpx.AsyncClient(
        trust_env=False, transport=_BoundedTransport(), headers=headers, **kwargs
    )


SOURCE = "configured Datasphere revenue view"
FIXTURE_SOURCE = "synthetic OAuth/OData fixture; no tenant proof"


def summarize_revenue(payload: dict, region: str, *, fixture: bool = False) -> str:
    if (
        not isinstance(payload, dict)
        or payload.get("source") != SOURCE
        or type(payload.get("limit")) is not int
        or payload["limit"] != LIMIT
        or not isinstance(payload.get("rows"), list)
        or len(payload["rows"]) > LIMIT
    ):
        raise ValueError("invalid revenue response scope")
    with localcontext() as context:
        context.prec = 40
        total = Decimal(0)
        for row in payload["rows"]:
            if (
                not isinstance(row, dict)
                or set(row) != {"Region", "Revenue"}
                or row["Region"] != region
            ):
                raise ValueError("invalid revenue row scope")
            value = row["Revenue"]
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError("invalid revenue value")
            try:
                if len(str(value)) > 64:
                    raise InvalidOperation
                amount = Decimal(str(value))
                if (
                    not amount.is_finite()
                    or abs(amount) > Decimal("1e20")
                    or amount.as_tuple().exponent < -12
                ):
                    raise InvalidOperation
                total += amount
            except (InvalidOperation, ValueError):
                raise ValueError("invalid revenue value") from None
    return json.dumps(
        {
            "region": region,
            "row_count": len(payload["rows"]),
            "revenue": format(total, "f"),
            "limit": LIMIT,
            "bounded": True,
            "source": FIXTURE_SOURCE if fixture else SOURCE,
        }
    )


def validated_mcp_url(value: str) -> str:
    try:
        url = urlsplit(value)
        port = url.port
        if url.username or url.password or url.query or url.fragment or not url.hostname:
            raise ValueError
        if url.scheme != "https" and (
            url.scheme != "http" or not ipaddress.ip_address(url.hostname).is_loopback
        ):
            raise ValueError
        if url.path != "/sse" or (url.scheme == "http" and port is None):
            raise ValueError
    except ValueError:
        raise ValueError(
            "MCP_SERVER_URL must be an approved HTTPS or loopback HTTP SSE URL"
        ) from None
    return value


async def read_region(region: str, limit: int) -> dict:
    token = _MCP_LOG_SCOPE.set(True)
    try:
        # The locked SDK logs before creating its client, including the first call.
        for name in (
            "mcp.client.sse",
            "httpx",
            "httpcore",
            "httpcore.connection",
            "httpcore.http11",
            "httpcore.http2",
            "httpcore.proxy",
            "httpcore.socks",
        ):
            logging.getLogger(name).addFilter(_SAFE_TRANSPORT_LOG)
        # Limit root validation logging to this call's async context.
        logging.getLogger().addFilter(_SAFE_ROOT_LOG)
        return await _read_region(region, limit)
    finally:
        _MCP_LOG_SCOPE.reset(token)


async def _read_region(region: str, limit: int) -> dict:
    url = validated_mcp_url(os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8091/sse"))
    async with asyncio.timeout(10):
        async with (
            sse_client(
                url,
                httpx_client_factory=bounded_mcp_client,
            ) as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            result = await session.call_tool(
                "read_region_revenue", {"region": region, "limit": limit}
            )
            if result.isError:
                raise RuntimeError("revenue tool failed")
            structured = getattr(result, "structuredContent", None)
            if structured is not None:
                return structured
            if len(result.content) != 1 or result.content[0].type != "text":
                raise ValueError("invalid revenue tool result")
            text = result.content[0].text
            if len(text.encode()) > MCP_RECEIVE_BYTES:
                raise ValueError("oversized revenue tool result")
            return json.loads(text)


class RevenueAgent:
    def __init__(self, *, caller=read_region, fixture: bool = False):
        self.caller = caller
        self.fixture = fixture

    async def invoke(self, text: str) -> str:
        prefix, separator, region = text.partition(" ")
        if prefix.lower() != "revenue" or not separator or not region.strip() or len(region) > 128:
            return "Use revenue <region> with a region of 1-128 characters."
        region = region.strip()
        payload = await self.caller(region, LIMIT)
        return summarize_revenue(payload, region, fixture=self.fixture)
