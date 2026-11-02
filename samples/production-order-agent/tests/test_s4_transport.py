"""Guard the S/4 transport without external services or credentials."""

import gzip
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from production_order_agent.mcp_server import S4Repository

ORDER = "7654321"
NAVIGATION = "to_ProductionOrderStatus"


@pytest.mark.parametrize("failure", ["http", "timeout", "network", "malformed"])
def test_backend_failure_hides_endpoint_and_driver_cause(failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private endpoint canary", request=request)
        if failure == "network":
            raise httpx.ConnectError("private endpoint canary", request=request)
        if failure == "malformed":
            return httpx.Response(200, text="private response canary")
        return httpx.Response(503, text="private response canary")

    repository = S4Repository(
        "https://private-endpoint-canary.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError) as error:
        repository.fetch(ORDER, NAVIGATION)
    diagnostic = "".join(traceback.format_exception(error.value))
    assert error.value.__suppress_context__ is True
    assert error.value.__cause__ is None
    assert not any(
        value in diagnostic
        for value in [
            "private endpoint canary",
            "private-endpoint-canary",
            "private response canary",
        ]
    )


def test_oversized_response_stops_stream_and_closes_transport():
    chunks = []
    closed = []

    class Oversized(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(32):
                chunks.append(index)
                yield b"x" * 65536

        def close(self):
            closed.append(True)

    repository = S4Repository(
        "https://fixture.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Oversized())),
    )
    with pytest.raises(RuntimeError, match="one MiB"):
        repository.fetch(ORDER, NAVIGATION)
    assert len(chunks) <= 17
    assert closed == [True]


def test_compressed_response_is_rejected_before_stream_read_and_closes():
    chunks, closed, requests = [], [], []

    class Compressed(httpx.SyncByteStream):
        def __iter__(self):
            chunks.append(True)
            yield gzip.compress(b"x" * 2097152)

        def close(self):
            closed.append(True)

    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=Compressed())

    repository = S4Repository(
        "https://fixture.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError, match="encoding must be identity"):
        repository.fetch(ORDER, NAVIGATION)
    assert requests[0].headers["Accept-Encoding"] == "identity"
    assert chunks == []
    assert closed == [True]


def test_loopback_backend_ignores_ambient_proxy(monkeypatch):
    records = [{"ManufacturingOrder": ORDER, "StatusName": "Fixture Released"}]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            body = json.dumps({"value": records}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    for name in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
        monkeypatch.setenv(name, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        repository = S4Repository(f"http://127.0.0.1:{server.server_port}/service", "synthetic-key")
        assert repository.fetch(ORDER, NAVIGATION) == records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        assert not thread.is_alive()
