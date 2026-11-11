"""Prove local A2A/MCP signal correlation and remove only owned test processes."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

SAMPLE = Path(__file__).resolve().parents[1]
MODELS = {
    "/v1/logs": ExportLogsServiceRequest,
    "/v1/metrics": ExportMetricsServiceRequest,
    "/v1/traces": ExportTraceServiceRequest,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_process(process: subprocess.Popen, port: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        require(process.poll() is None, "Owned smoke process stopped during startup")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("Owned smoke process did not start before the deadline")


def inspect_signals(received: list) -> dict:
    serialized = json.dumps(received)
    for canary in (
        "1000000",
        "prompt-privacy-canary",
        "ASSEMBLY",
        "Final assembly",
        "ManufacturingOrder",
        "http://",
        "api_key",
        "password",
    ):
        require(canary not in serialized, "A synthetic privacy canary entered exported signals")
    spans, logs, metrics = [], [], []
    for path, batch in received:
        if path == "/v1/traces":
            spans.extend(
                s for r in batch["resourceSpans"] for c in r["scopeSpans"] for s in c["spans"]
            )
        elif path == "/v1/logs":
            logs.extend(
                record
                for r in batch["resourceLogs"]
                for c in r["scopeLogs"]
                for record in c["logRecords"]
            )
        else:
            metrics.extend(
                m for r in batch["resourceMetrics"] for c in r["scopeMetrics"] for m in c["metrics"]
            )
    parents = [s for s in spans if s["name"] == "production_order.request"]
    require(len(parents) == 2, "Expected two request spans")
    require(len({s["traceId"] for s in parents}) == 2, "Concurrent traces mixed")
    for parent in parents:
        children = [s for s in spans if s.get("parentSpanId") == parent["spanId"]]
        require(
            {s["name"] for s in children}
            == {
                "get_production_order_status",
                "get_production_order_operations",
            }
            and len(children) == 2,
            "Expected both MCP child spans",
        )
        require(all(s["traceId"] == parent["traceId"] for s in children), "Child trace mismatch")
        require(
            len([record for record in logs if record["traceId"] == parent["traceId"]]) == 3,
            "Expected three correlated logs per request",
        )
    counters = [
        p
        for m in metrics
        if m["name"] == "production_order.requests"
        for p in m["sum"]["dataPoints"]
    ]
    histograms = [
        p
        for m in metrics
        if m["name"] == "production_order.duration"
        for p in m["histogram"]["dataPoints"]
    ]
    require(any(int(p["asInt"]) == 2 for p in counters), "Expected request counter of two")
    require(any(int(p["count"]) == 2 for p in histograms), "Expected duration count of two")
    exemplars = [e for p in histograms for e in p.get("exemplars", [])]
    require(bool(exemplars), "Expected a duration exemplar")
    require(
        all(e["traceId"] in {s["traceId"] for s in parents} for e in exemplars),
        "Exemplar trace mismatch",
    )
    require(
        all(not e.get("filteredAttributes") for e in exemplars), "Exemplar carries extra attributes"
    )
    return {
        "a2a_requests": 2,
        "request_spans": 2,
        "mcp_child_spans": 4,
        "correlated_logs": len(logs),
        "duration_exemplars": len(exemplars),
        "privacy_canaries_absent": True,
    }


def run() -> dict:
    received = []
    rejected = []
    delivery_available = True

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            model = MODELS.get(self.path)
            if model is None:
                self.send_error(404)
                return
            message = model()
            message.ParseFromString(self.rfile.read(int(self.headers["Content-Length"])))
            if not delivery_available:
                rejected.append(self.path)
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"synthetic-diagnostic-privacy-canary")
                return
            received.append((self.path, MessageToDict(message)))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    worker = threading.Thread(target=receiver.serve_forever)
    worker.start()
    mcp_port, agent_port = free_port(), free_port()
    while agent_port == mcp_port:
        agent_port = free_port()
    processes = []
    environment = {
        "PATH": os.defpath,
        "PYTHONPATH": str(SAMPLE / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DATA_MODE": "mock",
        "LLM_PROVIDER": "mock",
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": str(mcp_port),
        "MCP_SERVER_URL": f"http://127.0.0.1:{mcp_port}/sse",
        "HOST": "127.0.0.1",
        "PORT": str(agent_port),
        "URL": f"http://127.0.0.1:{agent_port}",
        "TELEMETRY_MODE": "disabled",
    }
    try:
        with (
            tempfile.TemporaryDirectory() as directory,
            (Path(directory) / "processes.log").open("w") as log,
        ):
            mcp = subprocess.Popen(
                [sys.executable, "-m", "production_order_agent.mcp_server"],
                cwd=SAMPLE,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            processes.append(mcp)
            wait_for_process(mcp, mcp_port)
            environment.update(
                TELEMETRY_SCOPE="synthetic-signals",
                TELEMETRY_NAMESPACE="synthetic",
                OTEL_EXPORTER_OTLP_ENDPOINT=f"http://127.0.0.1:{receiver.server_port}",
            )

            def request(index):
                body = {
                    "jsonrpc": "2.0",
                    "id": str(index),
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": f"synthetic-{index}",
                            "role": "ROLE_USER",
                            "parts": [{"text": "prompt-privacy-canary order 1000000"}],
                        }
                    },
                }
                with httpx.Client(trust_env=False, timeout=10) as client:
                    response = client.post(
                        f"http://127.0.0.1:{agent_port}/",
                        json=body,
                        headers={"A2A-Version": "1.0"},
                    )
                    response.raise_for_status()
                    task = response.json()["result"]["task"]
                require(
                    task["status"]["state"] == "TASK_STATE_COMPLETED",
                    "A2A task did not complete",
                )
                require("Potential delay" in json.dumps(task), "Missing business reply")

            result = {"phases": {}}
            for phase in ("enabled", "receiver_failure", "recovered", "disabled"):
                delivery_available = phase != "receiver_failure"
                environment["TELEMETRY_MODE"] = "disabled" if phase == "disabled" else "otlp"
                first_received, first_rejected = len(received), len(rejected)
                agent = subprocess.Popen(
                    [sys.executable, "-m", "production_order_agent"],
                    cwd=SAMPLE,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(agent)
                wait_for_process(agent, agent_port)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    list(pool.map(request, range(2)))
                agent.terminate()
                agent.wait(timeout=15)
                require(
                    agent.returncode in (0, -signal.SIGTERM),
                    "Agent did not stop after its owned SIGTERM",
                )
                batch = received[first_received:]
                failures = rejected[first_rejected:]
                if phase in ("enabled", "recovered"):
                    result["phases"][phase] = inspect_signals(batch)
                    require(not failures, "Available receiver rejected telemetry")
                elif phase == "receiver_failure":
                    require(not batch, "Unavailable receiver accepted telemetry")
                    require(set(failures) == set(MODELS), "Failure did not exercise all exporters")
                    result["phases"][phase] = {
                        "a2a_requests": 2,
                        "business_replies_preserved": True,
                        "rejected_signals": sorted(set(failures)),
                    }
                else:
                    require(not batch and not failures, "Disabled agent attempted export")
                    result["phases"][phase] = {
                        "a2a_requests": 2,
                        "business_replies_preserved": True,
                        "export_attempts": 0,
                    }
            log.flush()
            require(
                "synthetic-diagnostic-privacy-canary"
                not in (Path(directory) / "processes.log").read_text(),
                "Receiver diagnostic entered application logs",
            )
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        receiver.shutdown()
        receiver.server_close()
        worker.join(timeout=5)
    require(not worker.is_alive(), "Owned receiver thread remains")
    for port in (mcp_port, agent_port, receiver.server_port):
        with socket.socket() as sock:
            require(sock.connect_ex(("127.0.0.1", port)) != 0, "Owned smoke port remains open")
    result["owned_processes_reaped"] = True
    result["owned_ports_closed"] = True
    result["scope"] = "Loopback HTTP and mock data only; no Cloud Logging backend"
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
