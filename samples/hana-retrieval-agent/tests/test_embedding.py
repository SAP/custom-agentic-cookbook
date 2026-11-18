import json
from types import SimpleNamespace

import httpx2
import pytest

from hana_retrieval.embedding import MODEL, embed
from hana_retrieval.repository import RetrievalError


class Deployment:
    model_name = MODEL
    url = "https://embedding.invalid/deployment"
    prediction_url = None

    def additional_request_body_kwargs(self):
        return {}


class Proxy:
    request_header = {"AI-Resource-Group": "synthetic-group"}

    def select_deployment(self, **kwargs):
        assert kwargs == {"model_name": MODEL}
        return Deployment()


class Stream(httpx2.SyncByteStream):
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
        self.closed = False

    def __iter__(self):
        yield self.payload

    def close(self):
        self.closed = True


@pytest.mark.parametrize("outcome", ["success", "unavailable", "timeout"])
def test_native_embedding_transport_is_bounded_single_attempt_and_closed(monkeypatch, outcome):
    sdk = pytest.importorskip("gen_ai_hub.proxy.native.openai")
    original = sdk.OpenAI
    requests, streams, clients = [], [], []

    def respond(request):
        requests.append(request)
        assert request.url.host == "embedding.invalid"
        assert request.url.path == "/deployment/embeddings"
        assert request.headers["AI-Resource-Group"] == "synthetic-group"
        payload = json.loads(request.content)
        assert payload["model"] == MODEL
        assert payload["input"] == "assembly delay"
        if outcome == "timeout":
            raise httpx2.ReadTimeout("private endpoint credential-canary", request=request)
        stream = Stream(
            {"error": {"message": "private endpoint credential-canary"}}
            if outcome == "unavailable"
            else {
                "object": "list",
                "model": MODEL,
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            }
        )
        streams.append(stream)
        return httpx2.Response(
            503 if outcome == "unavailable" else 200,
            headers={"content-type": "application/json"},
            stream=stream,
        )

    def factory(**kwargs):
        client = original(
            proxy_client=Proxy(),
            http_client=httpx2.Client(transport=httpx2.MockTransport(respond), trust_env=False),
            **kwargs,
        )
        clients.append(client)
        return client

    monkeypatch.setattr(sdk, "OpenAI", factory)
    if outcome == "success":
        assert embed("assembly delay", 3) == [0.1, 0.2, 0.3]
    else:
        with pytest.raises(RetrievalError, match="^AI Core embedding request failed$") as error:
            embed("assembly delay", 3)
        assert "credential-canary" not in str(error.value)
        assert error.value.__suppress_context__ is True
    assert len(requests) == 1
    assert requests[0].extensions["timeout"] == {
        "connect": 20.0,
        "read": 20.0,
        "write": 20.0,
        "pool": 20.0,
    }
    assert clients[0].is_closed()
    assert all(stream.closed for stream in streams)


@pytest.mark.parametrize("phase", ["constructor", "request", "close"])
def test_sdk_value_errors_are_redacted_and_clients_closed(monkeypatch, phase):
    sdk = pytest.importorskip("gen_ai_hub.proxy.native.openai")
    closed = []

    def create(**kwargs):
        if phase == "request":
            raise ValueError("private endpoint credential-canary")
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])

    def close():
        closed.append(True)
        if phase == "close":
            raise ValueError("private endpoint credential-canary")

    def factory(**kwargs):
        if phase == "constructor":
            raise ValueError("private endpoint credential-canary")
        return SimpleNamespace(embeddings=SimpleNamespace(create=create), close=close)

    monkeypatch.setattr(sdk, "OpenAI", factory)
    with pytest.raises(RetrievalError, match="^AI Core embedding request failed$") as error:
        embed("assembly delay", 3)
    assert "credential-canary" not in str(error.value)
    assert error.value.__suppress_context__ is True
    assert closed == ([] if phase == "constructor" else [True])


def test_vector_validation_remains_controlled_after_client_cleanup(monkeypatch):
    sdk = pytest.importorskip("gen_ai_hub.proxy.native.openai")
    closed = []
    client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
        ),
        close=lambda: closed.append(True),
    )
    monkeypatch.setattr(sdk, "OpenAI", lambda **kwargs: client)
    with pytest.raises(ValueError, match="dimension"):
        embed("assembly delay", 3)
    assert closed == [True]


@pytest.mark.parametrize("status", [200, 503])
def test_completed_sdk_requests_hide_endpoint_but_keep_application_logs(
    monkeypatch, caplog, status
):
    import importlib
    import logging

    from hana_retrieval import mcp_server

    sdk = pytest.importorskip("gen_ai_hub.proxy.native.openai")
    original = sdk.OpenAI
    requests, clients = [], []
    monkeypatch.setattr(Deployment, "url", "https://private-embedding-canary.invalid/deployment")

    def respond(request):
        requests.append(request)
        return httpx2.Response(
            status,
            json={
                "object": "list",
                "model": MODEL,
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    def factory(**kwargs):
        client = original(
            proxy_client=Proxy(),
            http_client=httpx2.Client(transport=httpx2.MockTransport(respond), trust_env=False),
            **kwargs,
        )
        clients.append(client)
        return client

    monkeypatch.setattr(sdk, "OpenAI", factory)
    loggers = [logging.getLogger(name) for name in ["httpx2", "httpcore2"]]
    previous_levels = [logger.level for logger in loggers]
    try:
        with caplog.at_level(logging.INFO):
            for logger in loggers:
                logger.setLevel(logging.NOTSET)
            importlib.reload(mcp_server)
            if status == 200:
                assert embed("assembly delay", 3) == [0.1, 0.2, 0.3]
            else:
                with pytest.raises(RetrievalError, match="^AI Core embedding request failed$"):
                    embed("assembly delay", 3)
            logging.getLogger("hana_retrieval").info("application diagnostic retained")
        assert len(requests) == 1 and clients[0].is_closed()
        assert "application diagnostic retained" in caplog.text
        assert not any(
            value in caplog.text for value in ["private-embedding-canary", "/deployment"]
        )
    finally:
        for logger, level in zip(loggers, previous_levels, strict=True):
            logger.setLevel(level)


def test_real_core2_transport_diagnostics_stay_quiet_with_application_debug(monkeypatch, caplog):
    import importlib
    import logging
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from hana_retrieval import mcp_server

    sdk = pytest.importorskip("gen_ai_hub.proxy.native.openai")
    original = sdk.OpenAI
    requests, clients = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps(
                {
                    "object": "list",
                    "model": MODEL,
                    "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(Deployment, "url", f"http://127.0.0.1:{server.server_port}/deployment")

    def factory(**kwargs):
        client = original(
            proxy_client=Proxy(), http_client=httpx2.Client(trust_env=False), **kwargs
        )
        clients.append(client)
        return client

    monkeypatch.setattr(sdk, "OpenAI", factory)
    core = logging.getLogger("httpcore2")
    previous_level = core.level
    try:
        core.setLevel(logging.NOTSET)
        importlib.reload(mcp_server)
        with caplog.at_level(logging.DEBUG):
            assert embed("assembly delay", 3) == [0.1, 0.2, 0.3]
            logging.getLogger("hana_retrieval").info("application diagnostic retained")
        assert len(requests) == 1 and requests[0]["input"] == "assembly delay"
        assert clients[0].is_closed()
        assert "application diagnostic retained" in caplog.text
        assert not any(record.name.startswith("httpcore2") for record in caplog.records)
    finally:
        core.setLevel(previous_level)
        server.shutdown()
        server.server_close()
        thread.join(5)
        assert not thread.is_alive()
