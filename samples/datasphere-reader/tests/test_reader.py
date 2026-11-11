import gzip

import httpx
import pytest

from datasphere import DatasphereReader, ReaderError


@pytest.mark.parametrize("field", ["base_url", "token_url"])
@pytest.mark.parametrize(
    "malformed_url",
    [
        "https://[private-tenant.example]/SPACE",
        "https://fixture-user:fixture-secret@private-tenant.example\uff0fSPACE",
        "https://private-tenant.example:private-port/SPACE",
        "https://private-tenant.example/SPACE\x00",
    ],
    ids=["ipv6", "nfkc", "port", "control"],
)
def test_malformed_endpoints_fail_safely_before_client_allocation(
    field, malformed_url, monkeypatch
):
    def unexpected_client(**_):
        pytest.fail("malformed endpoint was accepted before HTTP client allocation")

    monkeypatch.setattr(httpx, "AsyncClient", unexpected_client)
    configuration = {
        "base_url": "https://tenant.example/SPACE",
        "token_url": "https://auth.example/token",
        "space": "SPACE",
        "view": "SALES",
        "shape": "A",
        "client_id": "fixture-client",
        "client_secret": "fixture-secret",
        field: malformed_url,
    }
    with pytest.raises(ValueError, match="^endpoint is malformed$") as error:
        DatasphereReader(**configuration)
    assert error.value.__suppress_context__


def reader(handler, shape="A", clock=lambda: 0):
    return DatasphereReader(
        base_url="https://tenant.example/api/" + ("SPACE" if shape == "A" else "relational"),
        space="SPACE",
        view="SALES",
        shape=shape,
        token_url="https://auth.example/oauth/token",
        client_id="fixture-client",
        client_secret="fixture-secret",
        clock=clock,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize("shape", ["A", "B"])
async def test_shapes_pagination_and_string_filter(shape):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "auth.example":
            return httpx.Response(200, json={"access_token": "fixture-token", "expires_in": 60})
        assert request.headers["Authorization"] == "Bearer fixture-token"
        if shape == "B" and request.url.path.endswith("/SALES/"):
            return httpx.Response(200, json={"value": [{"name": "Rows", "url": "Rows"}]})
        if "$skiptoken" in request.url.params:
            return httpx.Response(200, json={"value": [{"Region": "O'Reilly", "Revenue": 20}]})
        assert request.url.params["$filter"] == "Region eq 'O''Reilly'"
        assert request.url.params["$select"] == "Region,Revenue"
        return httpx.Response(
            200,
            json={
                "value": [{"Region": "O'Reilly", "Revenue": 10}],
                "@odata.nextLink": request.url.path.rsplit("/", 1)[-1] + "?$skiptoken=second",
            },
        )

    async with reader(handler, shape) as client:
        rows = await client.read(
            select=["Region", "Revenue"], equal={"Region": "O'Reilly"}, limit=2
        )
    assert rows == [{"Region": "O'Reilly", "Revenue": 10}, {"Region": "O'Reilly", "Revenue": 20}]
    assert len([r for r in requests if r.url.host == "auth.example"]) == 1
    assert client.http.is_closed


async def test_expired_token_and_one_unauthorized_retry():
    now = [0]
    tokens = []
    reads = []

    def handler(request):
        if request.url.host == "auth.example":
            tokens.append(1)
            return httpx.Response(
                200, json={"access_token": f"token-{len(tokens)}", "expires_in": 20}
            )
        reads.append(request.headers["Authorization"])
        if len(reads) == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"value": [{"Revenue": 10}]})

    async with reader(handler, clock=lambda: now[0]) as client:
        await client.read(select=["Revenue"], limit=1)
        now[0] = 30
        await client.read(select=["Revenue"], limit=1)
    assert reads == ["Bearer token-1", "Bearer token-2", "Bearer token-3"]


@pytest.mark.parametrize(
    "next_link",
    [
        "https://other.example/rows",
        "//other.example/rows",
        "/api/other/rows",
        "SALES?$skiptoken=loop",
    ],
)
async def test_untrusted_or_repeated_continuation_is_rejected(next_link):
    def handler(request):
        if request.url.host == "auth.example":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 60})
        return httpx.Response(200, json={"value": [{"Revenue": 1}], "@odata.nextLink": next_link})

    async with reader(handler) as client:
        with pytest.raises(ReaderError):
            await client.read(select=["Revenue"], limit=5, max_pages=3)


@pytest.mark.parametrize(
    "next_link",
    [
        "https://[private-tenant.example]/SPACE/SALES",
        "https://fixture-user:fixture-secret@private-tenant.example\uff0fSPACE/SALES",
        "SALES?$skiptoken=private-cursor\x00",
    ],
    ids=["ipv6", "nfkc", "control"],
)
async def test_malformed_continuation_has_safe_error_and_closes_client(next_link):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "auth.example":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 60})
        return httpx.Response(200, json={"value": [], "@odata.nextLink": next_link})

    async with reader(handler) as client:
        with pytest.raises(ReaderError, match="^invalid OData continuation$") as error:
            await client.read(select=["Revenue"], limit=5)
    assert error.value.__suppress_context__
    assert client.http.is_closed
    assert len(requests) == 2


@pytest.mark.parametrize("status", [401, 403, 404, 500, 503])
async def test_failed_requests_have_safe_errors(status):
    def handler(request):
        if request.url.host == "auth.example":
            return httpx.Response(200, json={"access_token": "fixture-token", "expires_in": 60})
        return httpx.Response(status, text="private backend detail")

    async with reader(handler) as client:
        with pytest.raises(ReaderError) as error:
            await client.read(select=["Revenue"], limit=1)
    assert str(status) in str(error.value)
    assert not any(
        s in str(error.value)
        for s in ["fixture-secret", "fixture-token", "tenant.example", "private backend"]
    )
    assert client.http.is_closed


async def test_malformed_rows_and_timeout_fail():
    for behavior in ["malformed", "timeout"]:

        def handler(request, behavior=behavior):
            if request.url.host == "auth.example":
                return httpx.Response(200, json={"access_token": "token", "expires_in": 60})
            if behavior == "timeout":
                raise httpx.ReadTimeout("private endpoint", request=request)
            return httpx.Response(200, json={"value": [{"Wrong": 1}]})

        async with reader(handler) as client:
            with pytest.raises(ReaderError):
                await client.read(select=["Revenue"], limit=1)


async def test_inputs_are_bounded_before_network():
    calls = []
    async with reader(lambda request: calls.append(request)) as client:
        for kwargs in [
            {"select": ["Revenue"], "limit": 0},
            {"select": ["Revenue;drop"], "limit": 1},
            {"select": ["Revenue"], "equal": {"Region": "x" * 257}, "limit": 1},
        ]:
            with pytest.raises(ValueError):
                await client.read(**kwargs)
    assert calls == []


async def test_real_loopback_oauth_and_odata_socket_path(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            self.reply({"access_token": "fixture-token", "expires_in": 60})

        def do_GET(self):
            assert self.headers["Authorization"] == "Bearer fixture-token"
            self.reply({"value": [{"Region": "EMEA", "Revenue": 42}]})

        def reply(self, body):
            import json

            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        async with DatasphereReader(
            base_url=base + "/SPACE",
            space="SPACE",
            view="SALES",
            shape="A",
            token_url=base + "/token",
            client_id="fixture-id",
            client_secret="fixture-secret",
            allow_http=True,
        ) as client:
            assert await client.read(
                select=["Region", "Revenue"], equal={"Region": "EMEA"}, limit=1
            ) == [{"Region": "EMEA", "Revenue": 42}]
        assert client.http.is_closed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize("phase", ["oauth", "odata"])
async def test_oversized_response_stops_reading_and_closes_http_client(phase):
    chunks = []

    class Oversized(httpx.AsyncByteStream):
        async def __aiter__(self):
            for index in range(32):
                chunks.append(index)
                yield b"x" * 65536

    def handler(request):
        if phase == "odata" and request.url.host == "auth.example":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 60})
        return httpx.Response(200, stream=Oversized())

    async with reader(handler) as client:
        with pytest.raises(ReaderError, match="response exceeds") as error:
            await client.read(select=["Revenue"], limit=1)
    assert len(chunks) <= 17
    assert client.http.is_closed
    assert not any(value in str(error.value) for value in ["token", "tenant.example"])


@pytest.mark.parametrize("phase", ["oauth", "odata"])
async def test_compressed_response_is_rejected_before_reading_and_closes(phase):
    chunks, closed, requests = [], [], []

    class Compressed(httpx.AsyncByteStream):
        async def __aiter__(self):
            chunks.append(True)
            yield gzip.compress(b"x" * 2097152)

        async def aclose(self):
            closed.append(True)

    def handler(request):
        requests.append(request)
        if phase == "odata" and request.url.host == "auth.example":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 60})
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=Compressed())

    async with reader(handler) as client:
        with pytest.raises(ReaderError, match="encoding must be identity"):
            await client.read(select=["Revenue"], limit=1)
    assert requests[-1].headers["Accept-Encoding"] == "identity"
    assert chunks == []
    assert closed == [True]
    assert client.http.is_closed
