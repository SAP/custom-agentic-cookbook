"""Optional, payload-free application signals. Disabled unless explicitly selected."""

from __future__ import annotations

import logging
import os
import re
import threading
from contextlib import ExitStack, contextmanager, nullcontext, suppress
from contextvars import ContextVar
from time import perf_counter
from urllib.parse import urlsplit

_SIGNAL: ContextVar[RequestSignal | None] = ContextVar("production_order_signal", default=None)
_ACTIVE: ContextVar[Telemetry | None] = ContextVar("production_order_telemetry", default=None)
_TOOLS = frozenset({"get_production_order_status", "get_production_order_operations"})
_SCOPE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_NAMESPACE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class _SafeDiagnostics(logging.Filter):
    def filter(self, record):
        record.msg = "Telemetry delivery diagnostic"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


_DIAGNOSTICS = _SafeDiagnostics()
_DIAGNOSTIC_LOCK = threading.Lock()
_DIAGNOSTIC_USERS = 0
_DIAGNOSTIC_LOGGERS = []


def _diagnostics(acquire: bool) -> None:
    # SDK exporters log transport failures; sanitize only their own logger records.
    global _DIAGNOSTIC_USERS
    with _DIAGNOSTIC_LOCK:
        if acquire:
            _DIAGNOSTIC_USERS += 1
            for name in list(logging.Logger.manager.loggerDict):
                if name.startswith(("opentelemetry.sdk.", "opentelemetry.exporter.")):
                    logger = logging.getLogger(name)
                    if logger not in _DIAGNOSTIC_LOGGERS:
                        logger.addFilter(_DIAGNOSTICS)
                        _DIAGNOSTIC_LOGGERS.append(logger)
        else:
            _DIAGNOSTIC_USERS -= 1
            if not _DIAGNOSTIC_USERS:
                for logger in _DIAGNOSTIC_LOGGERS:
                    logger.removeFilter(_DIAGNOSTICS)
                _DIAGNOSTIC_LOGGERS.clear()


def _check_ambient_configuration() -> None:
    if "OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED" in os.environ:
        raise ValueError("Telemetry does not accept ambient SDK internal metrics configuration")
    if any(
        key.startswith("OTEL_EXPORTER_OTLP_") and key != "OTEL_EXPORTER_OTLP_ENDPOINT"
        for key in os.environ
    ):
        raise ValueError("Telemetry accepts only the explicit OTLP endpoint configuration")


def _cleanup(callback, *args, **kwargs) -> None:
    with suppress(Exception):
        callback(*args, **kwargs)


class RequestSignal:
    def __init__(self, span):
        self.span = span
        self.outcome = "success"

    def fail(self):
        from opentelemetry.trace import StatusCode

        self.outcome = "error"
        self.span.set_status(StatusCode.ERROR)


class Telemetry:
    """Own providers per application; never replace global logging or OTel providers."""

    def __init__(
        self,
        *,
        endpoint: str = "",
        scope: str = "",
        namespace: str = "",
        span_exporter=None,
        log_exporter=None,
        metric_reader=None,
    ) -> None:
        self.endpoint = endpoint
        self.scope = scope
        self.namespace = namespace
        self.span_exporter = span_exporter
        self.log_exporter = log_exporter
        self.metric_reader = metric_reader
        self.providers: tuple = ()
        self.tracer = None
        self.logger = None
        self.requests = None
        self.duration = None

    @classmethod
    def from_env(cls) -> Telemetry:
        mode = os.getenv("TELEMETRY_MODE", "disabled")
        if mode == "disabled":
            return cls()
        if mode != "otlp":
            raise ValueError("TELEMETRY_MODE must be disabled or otlp")
        _check_ambient_configuration()
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "Telemetry requires an explicit HTTP OTLP endpoint without credentials"
            )
        try:
            port = parsed.port
            if port is not None and not 1 <= port <= 65535:
                raise ValueError("port is out of range")
        except ValueError as exc:
            raise ValueError("Telemetry endpoint has an invalid port") from exc
        scope = os.getenv("TELEMETRY_SCOPE", "")
        namespace = os.getenv("TELEMETRY_NAMESPACE", "")
        if not _SCOPE.fullmatch(scope) or not _NAMESPACE.fullmatch(namespace):
            raise ValueError("Telemetry requires a bounded scope and namespace")
        return cls(endpoint=endpoint.rstrip("/"), scope=scope, namespace=namespace)

    def start(self) -> None:
        if self.providers or not (self.endpoint or self.span_exporter):
            return
        _check_ambient_configuration()
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider, TraceBasedExemplarFilter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON

        if self.endpoint:
            import requests
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Register rollback before allocating transports, workers or providers.
        with ExitStack() as rollback:
            _diagnostics(True)
            rollback.callback(_cleanup, _diagnostics, False)

            def own(value, **shutdown_options):
                rollback.callback(_cleanup, value.shutdown, **shutdown_options)
                return value

            # Do not discover host, environment, identity or process resource attributes.
            resource = Resource(
                {
                    "service.name": "production-order-agent",
                    "cookbook.telemetry.scope": self.scope,
                    "k8s.namespace.name": self.namespace,
                }
            )
            if self.endpoint:

                def session():
                    value = requests.Session()
                    rollback.callback(_cleanup, value.close)
                    value.trust_env = False
                    return value

                options = {"headers": {}, "timeout": 1}
                span_exporter = own(
                    OTLPSpanExporter(
                        endpoint=self.endpoint + "/v1/traces", session=session(), **options
                    )
                )
                log_exporter = own(
                    OTLPLogExporter(
                        endpoint=self.endpoint + "/v1/logs", session=session(), **options
                    )
                )
                metric_exporter = own(
                    OTLPMetricExporter(
                        endpoint=self.endpoint + "/v1/metrics", session=session(), **options
                    )
                )
                metric_reader = own(
                    PeriodicExportingMetricReader(
                        metric_exporter,
                        export_interval_millis=60000,
                        export_timeout_millis=2000,
                    ),
                    timeout_millis=2000,
                )
                span_processor = own(
                    BatchSpanProcessor(
                        span_exporter,
                        max_queue_size=128,
                        max_export_batch_size=64,
                        schedule_delay_millis=5000,
                        export_timeout_millis=2000,
                    )
                )
                log_processor = own(
                    BatchLogRecordProcessor(
                        log_exporter,
                        max_queue_size=128,
                        max_export_batch_size=64,
                        schedule_delay_millis=5000,
                        export_timeout_millis=2000,
                    )
                )
            else:
                span_exporter, log_exporter, metric_reader = (
                    self.span_exporter,
                    self.log_exporter,
                    self.metric_reader,
                )
                span_processor = own(SimpleSpanProcessor(span_exporter))
                log_processor = own(SimpleLogRecordProcessor(log_exporter))
                own(metric_reader, timeout_millis=2000)
            traces = own(
                TracerProvider(resource=resource, sampler=ALWAYS_ON, shutdown_on_exit=False)
            )
            logs = own(LoggerProvider(resource=resource, shutdown_on_exit=False))
            meters = own(
                MeterProvider(
                    resource=resource,
                    metric_readers=[metric_reader],
                    exemplar_filter=TraceBasedExemplarFilter(),
                    shutdown_on_exit=False,
                ),
                timeout_millis=2000,
            )
            traces.add_span_processor(span_processor)
            logs.add_log_record_processor(log_processor)
            tracer = traces.get_tracer("production_order_agent")
            logger = logs.get_logger("production_order_agent")
            meter = meters.get_meter("production_order_agent")
            requests_counter = meter.create_counter("production_order.requests")
            duration = meter.create_histogram("production_order.duration", unit="s")

            # Normal ownership begins only after every startup operation succeeds.
            self.span_exporter, self.log_exporter, self.metric_reader = (
                span_exporter,
                log_exporter,
                metric_reader,
            )
            self.providers = (traces, logs, meters)
            self.tracer, self.logger = tracer, logger
            self.requests, self.duration = requests_counter, duration
            rollback.pop_all()

    def shutdown(self) -> None:
        for provider in self.providers:
            with suppress(Exception):
                provider.force_flush(timeout_millis=2000)
            with suppress(Exception):
                if provider is self.providers[-1]:
                    provider.shutdown(timeout_millis=2000)
                else:
                    provider.shutdown()
        if self.providers:
            _diagnostics(False)
        self.providers = ()
        self.tracer = None

    def _event(self, name: str, outcome: str) -> None:
        # Export failures never replace the business response; emit only fixed fields.
        with suppress(Exception):
            self.logger.emit(body=name, attributes={"outcome": outcome, "event.name": name})

    @contextmanager
    def request(self):
        if self.tracer is None:
            yield
            return
        from opentelemetry.context import Context

        token = _ACTIVE.set(self)
        began = perf_counter()
        try:
            with self.tracer.start_as_current_span(
                "production_order.request",
                context=Context(),
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                signal = RequestSignal(span)
                signal_token = _SIGNAL.set(signal)
                try:
                    yield signal
                except BaseException:
                    signal.fail()
                    raise
                finally:
                    outcome = signal.outcome
                    span.set_attribute("outcome", outcome)
                    with suppress(Exception):
                        self.requests.add(1, {"outcome": outcome})
                        self.duration.record(perf_counter() - began, {"outcome": outcome})
                    self._event("request.completed", outcome)
                    _SIGNAL.reset(signal_token)
        finally:
            _ACTIVE.reset(token)

    @contextmanager
    def tool(self, name: str):
        outcome = "success"
        with self.tracer.start_as_current_span(
            name,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield
            except BaseException:
                outcome = "error"
                from opentelemetry.trace import StatusCode

                span.set_status(StatusCode.ERROR)
                raise
            finally:
                span.set_attribute("outcome", outcome)
                self._event("tool.completed", outcome)


def decline_request() -> None:
    signal = _SIGNAL.get()
    if signal is not None:
        signal.outcome = "declined"


def tool_span(name: str):
    telemetry = _ACTIVE.get()
    if telemetry is None or name not in _TOOLS:
        return nullcontext()
    return telemetry.tool(name)
