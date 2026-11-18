"""Locked MCP protocol failures are bounded before decoding and safe in logs."""

import asyncio
import gzip
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from mcp import types

import revenue_agent

CANARY = "private-session-response-canary"
MAX_BYTES = 65536


class ProtocolStream(httpx.AsyncByteStream):
    def __init__(self, mode):
        self.mode = mode
        self.messages = asyncio.Queue()
        self.closed = False
        self.delivered = 0

    async def __aiter__(self):
        endpoint = (
            "https://outside.example/" + CANARY
            if self.mode == "origin"
            else "/messages?sessionId=" + CANARY
        )
        yield f"event: endpoint\ndata: {endpoint}\n\n".encode()
        while True:
            event = await self.messages.get()
            for offset in range(0, len(event), 1024):
                chunk = event[offset : offset + 1024]
                self.delivered += len(chunk)
                yield chunk

    async def aclose(self):
        self.closed = True


class Protocol:
    def __init__(self, mode):
        self.mode = mode
        self.stream = ProtocolStream(mode)
        self.transport_closed = False

    async def handle(self, request):
        if request.method == "GET":
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=self.stream
            )
        if self.mode == "post500":
            return httpx.Response(500, text=CANARY)
        message = json.loads(request.content)
        if "id" not in message:
            return httpx.Response(202)
        if self.mode == "invalid_request":
            event = (
                "event: message\ndata: "
                + json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 991,
                        "method": "sampling/createMessage",
                        "params": {"messages": CANARY},
                    }
                )
                + "\n\n"
            ).encode()
        elif self.mode == "malformed":
            event = f"event: message\ndata: {CANARY}\n\n".encode()
        else:
            if message["method"] == "initialize":
                result = {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "serverInfo": {"name": "fixture", "version": "1"},
                }
            else:
                payload = {
                    "rows": [],
                    "limit": 50,
                    "source": "configured Datasphere revenue view",
                    "unused": CANARY + "x" * (70000 if self.mode != "healthy" else 0),
                }
                result = (
                    {"content": [], "structuredContent": payload}
                    if self.mode == "structured"
                    else {"content": [{"type": "text", "text": json.dumps(payload)}]}
                )
            event = (
                "event: message\ndata: "
                + json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result})
                + "\n\n"
            ).encode()
        await self.stream.messages.put(event)
        return httpx.Response(202)


@pytest.fixture
def install_protocol(monkeypatch):
    def install(mode):
        protocol = Protocol(mode)
        transport = httpx.MockTransport(protocol.handle)
        original_close = transport.aclose

        async def close():
            protocol.transport_closed = True
            await original_close()

        transport.aclose = close
        monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **_: transport)
        original_client = httpx.AsyncClient

        def client(**kwargs):
            kwargs.setdefault("transport", transport)
            return original_client(**kwargs)

        monkeypatch.setattr(revenue_agent.httpx, "AsyncClient", client)
        monkeypatch.setenv("MCP_SERVER_URL", "http://127.0.0.1:8091/sse")
        return protocol

    return install


@pytest.mark.parametrize("mode", ["post500", "origin", "malformed", "invalid_request"])
async def test_protocol_failure_never_logs_endpoint_session_or_parse_canary(
    mode, install_protocol, caplog
):
    protocol = install_protocol(mode)
    caplog.set_level(logging.DEBUG)
    before = time.monotonic()
    with pytest.raises((ExceptionGroup, TimeoutError)):
        await asyncio.wait_for(revenue_agent.read_region("EMEA", 50), 0.5)
    assert time.monotonic() - before < 1
    assert protocol.stream.closed and protocol.transport_closed
    assert CANARY not in caplog.text
    assert "outside.example" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("mode", ["text", "structured"])
async def test_oversized_tool_event_refused_before_locked_sdk_json_decode(
    mode, install_protocol, monkeypatch
):
    protocol = install_protocol(mode)
    lengths = []
    original = types.JSONRPCMessage.model_validate_json

    def decode(data, **kwargs):
        lengths.append(len(data.encode()))
        return original(data, **kwargs)

    monkeypatch.setattr(types.JSONRPCMessage, "model_validate_json", decode)
    with pytest.raises((ExceptionGroup, TimeoutError)):
        await asyncio.wait_for(revenue_agent.read_region("EMEA", 50), 0.5)
    assert lengths and max(lengths) <= MAX_BYTES
    assert protocol.stream.delivered <= MAX_BYTES + 1024
    assert protocol.stream.closed and protocol.transport_closed


async def test_compressed_event_rejected_before_httpx_decompression(monkeypatch):
    compressed = gzip.compress(b"data: " + b"x" * 70000 + b"\n\n")
    closed, delivered = [], []

    class CompressedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            delivered.append(True)
            yield compressed

        async def aclose(self):
            closed.append(True)

    async def response(_):
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream", "content-encoding": "gzip"},
            stream=CompressedStream(),
        )

    transport = httpx.MockTransport(response)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **_: transport)
    original_client = httpx.AsyncClient

    def client(**kwargs):
        kwargs.setdefault("transport", transport)
        return original_client(**kwargs)

    monkeypatch.setattr(revenue_agent.httpx, "AsyncClient", client)
    with pytest.raises((ExceptionGroup, TimeoutError)):
        await asyncio.wait_for(revenue_agent.read_region("EMEA", 50), 0.5)
    assert closed and not delivered


def test_fresh_imported_consumer_redacts_first_configured_endpoint_log():
    scenario = """
import asyncio
import io
import json
import logging
import httpx
import revenue_agent
capture = io.StringIO()
handler = logging.StreamHandler(capture)
root = logging.getLogger()
root.handlers = [handler]
root.setLevel(logging.DEBUG)
attempts = []
async def fail(request):
    attempts.append(request.method)
    raise httpx.ConnectError("synthetic failure", request=request)
httpx.AsyncHTTPTransport = lambda **kwargs: httpx.MockTransport(fail)
async def run():
    try:
        await revenue_agent.read_region("EMEA", 50)
    except Exception:
        pass
asyncio.run(run())
print(json.dumps({"attempts": attempts, "logs": capture.getvalue()}))
"""
    canary_host = "private-first-call-canary.example"
    result = subprocess.run(
        [sys.executable, "-c", scenario],
        cwd=Path(revenue_agent.__file__).parent,
        env={**os.environ, "MCP_SERVER_URL": f"https://{canary_host}/sse"},
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["attempts"] == ["GET"]  # Only the fake transport receives a request.
    assert canary_host not in receipt["logs"]
    assert canary_host not in result.stderr


@pytest.mark.parametrize(
    "logger_name",
    [
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
    ],
)
def test_fresh_imported_consumer_redacts_explicit_httpcore_child_debug(logger_name):
    scenario = """
import asyncio
import io
import json
import logging
import os
import httpx
from httpcore._trace import Trace
import revenue_agent
capture = io.StringIO()
root = logging.getLogger()
root.handlers = [logging.StreamHandler(capture)]
root.setLevel(logging.DEBUG)
child = logging.getLogger(os.environ["TRACE_LOGGER_NAME"])
child.setLevel(logging.DEBUG)
attempts = []
async def fail(request):
    attempts.append(request.method)
    async with Trace("connect_tcp", child, kwargs={
        "host": "private-debug-host-canary.example",
        "headers": [(b"Authorization", b"private-debug-header-canary")],
    }):
        raise httpx.ConnectError("private-debug-exception-canary", request=request)
httpx.AsyncHTTPTransport = lambda **kwargs: httpx.MockTransport(fail)
async def run():
    try:
        await revenue_agent.read_region("EMEA", 50)
    except Exception:
        pass
asyncio.run(run())
print(json.dumps({"attempts": attempts, "logs": capture.getvalue()}))
"""
    result = subprocess.run(
        [sys.executable, "-c", scenario],
        cwd=Path(revenue_agent.__file__).parent,
        env={
            **os.environ,
            "MCP_SERVER_URL": "https://private-debug-host-canary.example/sse",
            "TRACE_LOGGER_NAME": logger_name,
        },
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["attempts"] == ["GET"]
    for canary in (
        "private-debug-host-canary.example",
        "private-debug-header-canary",
        "private-debug-exception-canary",
    ):
        assert canary not in receipt["logs"]
        assert canary not in result.stderr
