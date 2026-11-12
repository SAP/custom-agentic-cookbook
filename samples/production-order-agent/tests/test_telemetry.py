from __future__ import annotations

import asyncio
import json

import pytest
from starlette.testclient import TestClient

from production_order_agent.__main__ import create_app
from production_order_agent.agent import ProductionOrderAgent
from production_order_agent.settings import Settings
from production_order_agent.telemetry import Telemetry, tool_span


def request(text: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "SendMessage",
        "params": {
            "message": {"messageId": "synthetic", "role": "ROLE_USER", "parts": [{"text": text}]}
        },
    }


@pytest.fixture
def signals():
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    spans, logs, reader = (
        InMemorySpanExporter(),
        InMemoryLogRecordExporter(),
        InMemoryMetricReader(),
    )
    telemetry = Telemetry(span_exporter=spans, log_exporter=logs, metric_reader=reader)
    return telemetry, spans, logs, reader


def test_disabled_needs_no_optional_imports_or_export(monkeypatch):
    import builtins

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise AssertionError("disabled telemetry imports optional package")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://credentials.invalid/private")
    monkeypatch.setenv("TELEMETRY_MODE", "disabled")
    telemetry = Telemetry.from_env()
    telemetry.start()
    with telemetry.request(), tool_span("get_production_order_status"):
        pass
    telemetry.shutdown()


def test_a2a_request_emits_three_correlated_payload_free_signals(signals):
    telemetry, spans, logs, reader = signals

    async def call(_, tool, __):
        with tool_span(tool):
            await asyncio.sleep(0)
            return [{"private_order_record_canary": "secret-record"}]

    agent = ProductionOrderAgent(Settings(), tool_caller=call)
    with TestClient(create_app(agent=agent, telemetry=telemetry)) as client:
        response = client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json=request("prompt-canary production order 987654321"),
        )
        data = reader.get_metrics_data()
    assert response.json()["result"]["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    finished = spans.get_finished_spans()
    parent = next(s for s in finished if s.name == "production_order.request")
    children = [s for s in finished if s.parent]
    assert {s.name for s in children} == {
        "get_production_order_status",
        "get_production_order_operations",
    }
    assert all(s.context.trace_id == parent.context.trace_id for s in children)
    assert all(s.parent.span_id == parent.context.span_id for s in children)
    records = [r.log_record for r in logs.get_finished_logs()]
    assert len(records) == 3
    assert all(r.trace_id == parent.context.trace_id for r in records)
    metrics = {
        m.name: m
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for m in scope.metrics
    }
    counter = metrics["production_order.requests"].data.data_points[0]
    duration = metrics["production_order.duration"].data.data_points[0]
    assert counter.value == 1
    assert dict(counter.attributes) == {"outcome": "success"}
    assert duration.count == 1 and duration.sum >= 0
    assert duration.exemplars[0].trace_id == parent.context.trace_id
    assert not duration.exemplars[0].filtered_attributes
    serialized = json.dumps(
        [s.to_json() for s in finished]
        + [{"body": r.body, "attributes": dict(r.attributes)} for r in records]
    )
    serialized += json.dumps(data.to_json())
    serialized += json.dumps([dict(r.resource.attributes) for r in logs.get_finished_logs()])
    for canary in ("987654321", "prompt-canary", "private_order_record_canary", "secret-record"):
        assert canary not in serialized


@pytest.mark.asyncio
async def test_concurrent_request_contexts_do_not_mix(signals):
    telemetry, spans, logs, reader = signals
    telemetry.start()

    async def operation():
        with telemetry.request():

            async def tool(name):
                with tool_span(name):
                    await asyncio.sleep(0)

            await asyncio.gather(
                tool("get_production_order_status"), tool("get_production_order_operations")
            )

    await asyncio.gather(operation(), operation())
    parents = [s for s in spans.get_finished_spans() if not s.parent]
    assert len(parents) == 2 and len({s.context.trace_id for s in parents}) == 2
    for parent in parents:
        children = [
            s
            for s in spans.get_finished_spans()
            if s.context.trace_id == parent.context.trace_id and s.parent
        ]
        assert len(children) == 2
        assert all(s.parent.span_id == parent.context.span_id for s in children)
    telemetry.shutdown()


def test_error_outcome_is_safe(signals):
    telemetry, spans, logs, reader = signals

    class Failing:
        async def invoke(self, text):
            raise RuntimeError("credential-canary https://private.invalid/?token=secret")

    with TestClient(create_app(agent=Failing(), telemetry=telemetry)) as client:
        response = client.post("/", headers={"A2A-Version": "1.0"}, json=request("private prompt"))
        data = reader.get_metrics_data()
    assert response.json()["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
    parent = spans.get_finished_spans()[0]
    assert dict(parent.attributes) == {"outcome": "error"}
    assert not parent.events and parent.status.description is None
    metrics = [m for r in data.resource_metrics for s in r.scope_metrics for m in s.metrics]
    assert all(dict(m.data.data_points[0].attributes) == {"outcome": "error"} for m in metrics)
    assert "credential-canary" not in parent.to_json()


def test_declined_request_counts_once_without_tools(signals):
    telemetry, spans, logs, reader = signals
    with TestClient(create_app(telemetry=telemetry)) as client:
        response = client.post("/", headers={"A2A-Version": "1.0"}, json=request("no order"))
        data = reader.get_metrics_data()
    assert "unambiguous" in response.text
    assert len(spans.get_finished_spans()) == 1
    assert dict(spans.get_finished_spans()[0].attributes) == {"outcome": "declined"}
    metrics = [m for r in data.resource_metrics for s in r.scope_metrics for m in s.metrics]
    assert (
        next(m for m in metrics if m.name == "production_order.requests").data.data_points[0].value
        == 1
    )


def test_rejects_ambient_otlp_credentials_without_printing_them(monkeypatch):
    monkeypatch.setenv("TELEMETRY_MODE", "otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    monkeypatch.setenv("TELEMETRY_SCOPE", "synthetic")
    monkeypatch.setenv("TELEMETRY_NAMESPACE", "synthetic")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "authorization=credential-canary")
    with pytest.raises(ValueError, match="explicit OTLP endpoint") as error:
        Telemetry.from_env()
    assert "credential-canary" not in str(error.value)


def test_exporter_exception_does_not_break_business_or_shutdown(signals, caplog):
    telemetry, spans, logs, reader = signals

    def failed(*args, **kwargs):
        raise RuntimeError("private exporter diagnostic")

    spans.export = failed
    spans.shutdown = failed
    with TestClient(create_app(telemetry=telemetry)) as client:
        response = client.post("/", headers={"A2A-Version": "1.0"}, json=request("no order"))
    assert "unambiguous" in response.text
    assert not telemetry.providers
    assert "private exporter diagnostic" not in caplog.text


@pytest.mark.parametrize(
    "key",
    [
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
        "OTEL_EXPORTER_OTLP_METRICS_HEADERS",
        "OTEL_EXPORTER_OTLP_CERTIFICATE",
        "OTEL_EXPORTER_OTLP_CLIENT_KEY",
        "OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE",
        "OTEL_EXPORTER_OTLP_LOGS_CLIENT_KEY",
        "OTEL_EXPORTER_OTLP_TIMEOUT",
        "OTEL_EXPORTER_OTLP_COMPRESSION",
    ],
)
def test_ambient_exporter_hooks_are_rejected_before_optional_import(monkeypatch, key):
    monkeypatch.setenv("TELEMETRY_MODE", "otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    monkeypatch.setenv("TELEMETRY_SCOPE", "synthetic")
    monkeypatch.setenv("TELEMETRY_NAMESPACE", "synthetic")
    monkeypatch.setenv(key, "credential-canary")
    with pytest.raises(ValueError, match="explicit OTLP endpoint configuration") as error:
        Telemetry.from_env()
    assert "credential-canary" not in str(error.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:4318/v1/traces",
        "https://user:secret@example.invalid",
        "http://127.0.0.1:70000",
        "http://127.0.0.1/?token=secret",
    ],
)
def test_otlp_requires_base_endpoint(monkeypatch, endpoint):
    monkeypatch.setenv("TELEMETRY_MODE", "otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)
    monkeypatch.setenv("TELEMETRY_SCOPE", "synthetic")
    monkeypatch.setenv("TELEMETRY_NAMESPACE", "synthetic")
    with pytest.raises(ValueError):
        Telemetry.from_env()


def test_ambient_resource_identity_is_not_exported(signals, monkeypatch):
    telemetry, spans, logs, reader = signals
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "user.id=credential-canary")
    telemetry.start()
    with telemetry.request():
        pass
    assert dict(spans.get_finished_spans()[0].resource.attributes) == {
        "service.name": "production-order-agent",
        "cookbook.telemetry.scope": "",
        "k8s.namespace.name": "",
    }
    telemetry.shutdown()


def test_sdk_diagnostic_filter_lives_until_both_apps_stop(signals, caplog):
    import logging

    from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    first = signals[0]
    second = Telemetry(
        span_exporter=InMemorySpanExporter(),
        log_exporter=InMemoryLogRecordExporter(),
        metric_reader=InMemoryMetricReader(),
    )
    logger = logging.getLogger("opentelemetry.sdk.trace.export")
    original = list(logger.filters)
    first.start()
    second.start()
    first.shutdown()
    logger.warning("https://private.invalid diagnostic-canary", exc_info=True)
    assert "diagnostic-canary" not in caplog.text
    assert "Telemetry delivery diagnostic" in caplog.text
    second.shutdown()
    assert logger.filters == original


def test_real_otlp_delivery_failure_preserves_reply_and_removes_workers(caplog):
    pytest.importorskip("opentelemetry.sdk")
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Unavailable(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"credential-diagnostic-canary")

        def log_message(self, *args):
            pass

    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Unavailable)
    worker = threading.Thread(target=receiver.serve_forever)
    worker.start()
    before = {thread.ident for thread in threading.enumerate()}
    telemetry = Telemetry(
        endpoint=f"http://127.0.0.1:{receiver.server_port}",
        scope="synthetic",
        namespace="synthetic",
    )
    try:
        with TestClient(create_app(telemetry=telemetry)) as client:
            response = client.post("/", headers={"A2A-Version": "1.0"}, json=request("no order"))
        assert "unambiguous" in response.text
        assert not telemetry.providers
        assert "credential-diagnostic-canary" not in caplog.text
        assert "http://127.0.0.1" not in caplog.text
        assert not [
            t for t in threading.enumerate() if t.ident not in before and t.name.startswith("Otel")
        ]
    finally:
        receiver.shutdown()
        receiver.server_close()
        worker.join(timeout=5)


def test_changed_environment_is_rejected_at_start(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    telemetry = Telemetry(
        endpoint="http://127.0.0.1:4318", scope="synthetic", namespace="synthetic"
    )
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_CLIENT_KEY", "credential-path-canary")
    with pytest.raises(ValueError) as error:
        telemetry.start()
    assert "credential-path-canary" not in str(error.value)
    assert not telemetry.providers


def test_request_does_not_export_ambient_trace_identity(signals):
    from opentelemetry.trace import (
        NonRecordingSpan,
        SpanContext,
        TraceFlags,
        TraceState,
        use_span,
    )

    telemetry, spans, logs, reader = signals
    telemetry.start()
    parent = NonRecordingSpan(
        SpanContext(123, 456, True, TraceFlags(1), TraceState([("tenant", "identity-canary")]))
    )
    with use_span(parent), telemetry.request(), tool_span("get_production_order_status"):
        pass
    finished = spans.get_finished_spans()
    request_span = next(s for s in finished if s.name == "production_order.request")
    child = next(s for s in finished if s.name == "get_production_order_status")
    assert request_span.parent is None
    assert request_span.context.trace_id != 123
    assert not request_span.context.trace_state
    assert child.parent.span_id == request_span.context.span_id
    assert child.context.trace_id == request_span.context.trace_id
    assert "identity-canary" not in json.dumps([s.to_json() for s in finished])
    telemetry.shutdown()


@pytest.mark.parametrize("failure", ["span_limit", "log_limit", "meter_provider", "instrument"])
def test_failed_startup_unwinds_workers_sessions_and_diagnostic_filters(failure):
    pytest.importorskip("opentelemetry.sdk")
    import os
    import subprocess
    import sys
    import textwrap

    # Isolate the red case so leaked daemon workers cannot contaminate later tests.
    script = textwrap.dedent("""\
        import logging
        import os
        import sys
        import threading
        import requests
        import opentelemetry.sdk.metrics as sdk_metrics
        import opentelemetry.sdk.trace as sdk_trace
        from production_order_agent.telemetry import Telemetry

        failure = sys.argv[1]
        sessions = []
        original_session = requests.Session
        class TrackedSession(original_session):
            def __init__(self):
                super().__init__()
                self.closed = False
                sessions.append(self)
            def close(self):
                self.closed = True
                super().close()
        requests.Session = TrackedSession
        def fail(*args, **kwargs):
            raise ValueError("synthetic startup failure")
        if failure == "span_limit":
            os.environ["OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT"] = "invalid"
        elif failure == "log_limit":
            os.environ["OTEL_LOGRECORD_ATTRIBUTE_COUNT_LIMIT"] = "invalid"
        elif failure == "meter_provider":
            sdk_metrics.MeterProvider = fail
        else:
            sdk_trace.TracerProvider.get_tracer = fail
        logger = logging.getLogger("opentelemetry.sdk.trace.export")
        original_filters = list(logger.filters)
        before = {thread.ident for thread in threading.enumerate()}
        telemetry = Telemetry(endpoint="http://127.0.0.1:4318",
                              namespace="synthetic", scope="synthetic")
        try:
            telemetry.start()
        except ValueError:
            pass
        else:
            raise AssertionError("startup must fail")
        telemetry.shutdown()
        assert not telemetry.providers and telemetry.tracer is None
        workers = [thread.name for thread in threading.enumerate()
                   if thread.ident not in before and thread.name.startswith("Otel")]
        assert not workers, workers
        assert len(sessions) == 3 and all(session.closed for session in sessions)
        assert logger.filters == original_filters
    """)
    environment = {key: value for key, value in os.environ.items() if key in {"PATH", "PYTHONPATH"}}
    result = subprocess.run(
        [sys.executable, "-c", script, failure],
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    assert result.returncode == 0, result.stderr


def test_lifespan_shuts_down_when_start_raises():
    class FailedStartup(Telemetry):
        stopped = False

        def start(self):
            raise ValueError("synthetic startup failure")

        def shutdown(self):
            self.stopped = True

    telemetry = FailedStartup()
    with (
        pytest.raises(ValueError, match="synthetic startup failure"),
        TestClient(create_app(telemetry=telemetry)),
    ):
        pass
    assert telemetry.stopped


@pytest.mark.parametrize("entry", ["from_env", "start"])
def test_sdk_internal_metrics_hook_cannot_export_endpoint_to_global_provider(monkeypatch, entry):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    monkeypatch.setattr(metrics, "get_meter_provider", lambda: provider)
    monkeypatch.setenv("TELEMETRY_MODE", "otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://endpoint-canary.invalid:4318")
    monkeypatch.setenv("TELEMETRY_SCOPE", "synthetic")
    monkeypatch.setenv("TELEMETRY_NAMESPACE", "synthetic")
    monkeypatch.setenv("OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED", "true")
    telemetry = Telemetry(
        endpoint="http://endpoint-canary.invalid:4318", scope="synthetic", namespace="synthetic"
    )
    try:
        with pytest.raises(ValueError, match="internal metrics"):
            Telemetry.from_env() if entry == "from_env" else telemetry.start()
        assert not telemetry.providers
        assert reader.get_metrics_data() is None
    finally:
        telemetry.shutdown()
        provider.shutdown()
