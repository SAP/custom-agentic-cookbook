"""Guard the S/4 transport without external services or credentials."""

import gzip
import json
import threading
import traceback
import tracemalloc
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from production_order_agent import mcp_server
from production_order_agent.mcp_server import S4Repository

ORDER = "7654321"
NAVIGATION = "to_ProductionOrderStatus"


@pytest.mark.parametrize(
    "tool_name", ["get_production_order_status", "get_production_order_operations"]
)
@pytest.mark.parametrize(
    "base_url",
    [
        "https://[private-tenant.example]/service",
        "https://fixture-user:fixture-secret@private-tenant.example\uff0fservice",
        "https://private-tenant.example:private-port/service",
        "https://private-tenant.example/service\x01",
    ],
    ids=["ipv6", "nfkc", "port", "control"],
)
async def test_malformed_endpoint_errors_are_safe_at_direct_mcp_boundary(
    tool_name, base_url, monkeypatch, caplog
):
    requests = []
    original_client = httpx.Client

    def unexpected_request(request):
        requests.append(request)
        pytest.fail("malformed endpoint reached the HTTP transport")

    def client_with_no_network(**kwargs):
        kwargs["transport"] = httpx.MockTransport(unexpected_request)
        return original_client(**kwargs)

    monkeypatch.setattr(httpx, "Client", client_with_no_network)
    monkeypatch.setenv("DATA_MODE", "s4")
    monkeypatch.setenv("S4_BASE_URL", base_url)
    monkeypatch.setenv("S4_API_KEY", "synthetic-parser-key")
    with pytest.raises(Exception) as error:
        await mcp_server.create_mcp_server().call_tool(tool_name, {"manufacturing_order": ORDER})
    diagnostic = "".join(traceback.format_exception(error.value)) + caplog.text
    assert "S/4 request could not reach the backend" in diagnostic
    assert not any(
        value in diagnostic
        for value in ["private-tenant", "private-port", "fixture-secret", "synthetic-parser-key"]
    )
    assert requests == []


@pytest.mark.parametrize("failure", ["http", "timeout", "network", "malformed"])
def test_backend_failure_hides_endpoint_and_driver_cause(failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private endpoint canary", request=request)
        if failure == "network":
            raise httpx.ConnectError("private endpoint canary", request=request)
        if failure == "malformed":
            return httpx.Response(200, stream=httpx.ByteStream(b"private response canary"))
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


@pytest.mark.parametrize("encoding", ["br", "gzip, deflate"])
def test_unsupported_encoding_is_rejected_before_stream_read_and_closes(encoding):
    chunks, closed, requests = [], [], []

    class Compressed(httpx.SyncByteStream):
        def __iter__(self):
            chunks.append(True)
            yield gzip.compress(b"x" * 2097152)

        def close(self):
            closed.append(True)

    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={"Content-Encoding": encoding}, stream=Compressed())

    repository = S4Repository(
        "https://fixture.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError, match="unsupported.*encoding"):
        repository.fetch(ORDER, NAVIGATION)
    assert requests[0].headers["Accept-Encoding"] == "identity"
    assert chunks == []
    assert closed == [True]


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
@pytest.mark.parametrize("chunk_size", [1, 65536])
def test_compressed_odata_returns_records_and_closes(encoding, compress, chunk_size):
    records = [{"ManufacturingOrder": ORDER, "StatusName": "Fixture Released"}]
    payload = compress(json.dumps({"d": {"results": records}}).encode())
    closed = []

    class Encoded(httpx.SyncByteStream):
        def __iter__(self):
            for start in range(0, len(payload), chunk_size):
                yield payload[start : start + chunk_size]

        def close(self):
            closed.append(True)

    repository = S4Repository(
        "https://fixture.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"Content-Encoding": encoding}, stream=Encoded())
        ),
    )
    assert repository.fetch(ORDER, NAVIGATION) == records
    assert closed == [True]


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
def test_decoded_size_limit_stops_compression_bomb_and_closes(encoding, compress):
    payload = compress(b"x" * (2 * mcp_server.MAX_RESPONSE_BYTES))
    assert len(payload) < mcp_server.MAX_RESPONSE_BYTES
    read, closed = [], []

    class Bomb(httpx.SyncByteStream):
        def __iter__(self):
            read.append(True)
            yield payload
            pytest.fail("oversized decoded response must stop the stream")

        def close(self):
            closed.append(True)

    repository = S4Repository(
        "https://fixture.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"Content-Encoding": encoding}, stream=Bomb())
        ),
    )
    with pytest.raises(RuntimeError, match="decoded.*one MiB"):
        repository.fetch(ORDER, NAVIGATION)
    assert read == [True]
    assert closed == [True]


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
def test_compression_bomb_is_rejected_before_large_decoded_allocation(encoding, compress):
    payload = compress(b"x" * (16 * mcp_server.MAX_RESPONSE_BYTES))
    repository = S4Repository(
        "https://fixture.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"Content-Encoding": encoding}, stream=httpx.ByteStream(payload)
            )
        ),
    )
    # Trace only the fetch, after constructing the adversarial input.
    tracemalloc.start()
    try:
        with pytest.raises(RuntimeError, match="decoded.*one MiB"):
            repository.fetch(ORDER, NAVIGATION)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 4 * mcp_server.MAX_RESPONSE_BYTES


def test_raw_size_limit_rejects_large_gzip_header_with_small_decoded_body():
    compressed = gzip.compress(b'{"value": []}')
    # A valid gzip filename can exceed the raw cap without expanding the JSON.
    payload = compressed[:3] + b"\x08" + compressed[4:10]
    payload += b"x" * (2 * mcp_server.MAX_RESPONSE_BYTES) + b"\x00" + compressed[10:]
    assert gzip.decompress(payload) == b'{"value": []}'
    read, closed = [], []

    class LargeHeader(httpx.SyncByteStream):
        def __iter__(self):
            for start in range(0, len(payload), 65536):
                read.append(True)
                yield payload[start : start + 65536]

        def close(self):
            closed.append(True)

    repository = S4Repository(
        "https://fixture.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"Content-Encoding": "gzip"}, stream=LargeHeader()
            )
        ),
    )
    with pytest.raises(RuntimeError, match="raw.*one MiB"):
        repository.fetch(ORDER, NAVIGATION)
    assert len(read) <= 17
    assert closed == [True]


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
def test_decoded_body_at_exact_limit_is_accepted(encoding, compress):
    prefix, suffix = b'{"padding":"', b'","value":[]}'
    body = prefix + b"x" * (mcp_server.MAX_RESPONSE_BYTES - len(prefix + suffix)) + suffix
    payload = compress(body)
    repository = S4Repository(
        "https://fixture.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"Content-Encoding": encoding}, stream=httpx.ByteStream(payload)
            )
        ),
    )
    assert repository.fetch(ORDER, NAVIGATION) == []


@pytest.mark.parametrize("chunk_size", [1, 65536])
def test_concatenated_gzip_members_form_one_json_document(chunk_size):
    payload = gzip.compress(b'{"value":') + gzip.compress(b"[]}")

    class Members(httpx.SyncByteStream):
        def __iter__(self):
            for start in range(0, len(payload), chunk_size):
                yield payload[start : start + chunk_size]

    repository = S4Repository(
        "https://fixture.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=Members())
        ),
    )
    assert repository.fetch(ORDER, NAVIGATION) == []


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
@pytest.mark.parametrize("damage", ["invalid", "truncated", "trailing"])
def test_malformed_compression_has_safe_diagnostic_and_closes(encoding, compress, damage):
    payload = compress(b'{"value": []}')
    if damage == "invalid":
        payload = b"private response canary"
    elif damage == "truncated":
        payload = payload[:-1]
    else:
        payload += b"private response canary"
    closed = []

    class Damaged(httpx.SyncByteStream):
        def __iter__(self):
            yield payload

        def close(self):
            closed.append(True)

    repository = S4Repository(
        "https://private-endpoint-canary.example/service",
        "synthetic-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"Content-Encoding": encoding}, stream=Damaged())
        ),
    )
    with pytest.raises(RuntimeError, match="malformed compressed response") as error:
        repository.fetch(ORDER, NAVIGATION)
    assert error.value.__suppress_context__ is True
    diagnostic = "".join(traceback.format_exception(error.value))
    assert "private response canary" not in diagnostic
    assert "private-endpoint-canary" not in diagnostic
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
