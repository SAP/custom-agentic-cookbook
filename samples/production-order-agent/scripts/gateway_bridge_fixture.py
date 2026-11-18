import gzip
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import zlib
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

ORDER = "7654321"
STATUSES = [{"ManufacturingOrder": ORDER, "StatusCode": "FIX1", "StatusName": "Fixture Released"}]
OPERATIONS = [
    {
        "ManufacturingOrder": ORDER,
        "ManufacturingOrderOperation": "0099",
        "MfgOrderOperationText": "Fixture inspection",
        "WorkCenter": "FIXTURE-WC",
        "OpErlstSchedldExecEndDte": "2001-01-01",
        "OperationIsFinallyConfirmed": False,
    },
    {
        "ManufacturingOrder": ORDER,
        "ManufacturingOrderOperation": "0100",
        "MfgOrderOperationText": "Fixture packing",
        "WorkCenter": "FIXTURE-WC",
        "OpErlstSchedldExecEndDte": "2001-01-01",
        "OperationIsFinallyConfirmed": True,
    },
]
state = {
    "encoding": "gzip",
    "data": "ok",
    "oauth": "ok",
    "inference": "ok",
    "data_calls": 0,
    "oauth_calls": 0,
    "inference_calls": 0,
    "qwen_calls": 0,
}
lock = threading.Lock()


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, payload, encoding="identity"):
        body = json.dumps(payload).encode()
        if encoding == "gzip":
            body = gzip.compress(body)
        elif encoding == "deflate":
            body = zlib.compress(body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Encoding", encoding)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        with suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)

    def do_GET(self):
        if self.path == "/state":
            with lock:
                snapshot = dict(state)
            return self.reply(200, snapshot)
        assert self.headers.get("APIKey") == "synthetic-fixture-key"
        assert self.headers.get("Accept-Encoding") == "identity"
        assert f"A_ProductionOrder_2('{ORDER}')" in self.path
        with lock:
            state["data_calls"] += 1
            encoding, data_mode = state["encoding"], state["data"]
        if data_mode == "refuse":
            return self.reply(503, {"error": "synthetic-response-canary"})
        records = STATUSES if "to_ProductionOrderStatus" in self.path else OPERATIONS
        self.reply(200, {"d": {"results": records}}, encoding)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/control":
            assert self.headers.get("Authorization") == "Bearer synthetic-control-token"
            update = json.loads(body)
            assert set(update) <= {"encoding", "data", "oauth", "inference"}
            with lock:
                state.update(update)
            return self.reply(200, {"updated": True})
        if self.path == "/oauth/token":
            assert self.headers.get("Authorization", "").startswith("Basic ")
            with lock:
                state["oauth_calls"] += 1
                mode = state["oauth"]
            if mode == "refuse":
                return self.reply(401, {"error": "synthetic-oauth-canary"})
            return self.reply(
                200,
                {"access_token": "synthetic-oauth-token", "token_type": "Bearer", "expires_in": 60},
            )
        assert self.path == "/v1/chat/completions"
        assert self.headers.get("Authorization") == "Bearer synthetic-oauth-token"
        assert b"synthetic-fixture-key" not in body
        assert b"synthetic-bridge-token" not in body
        payload = json.loads(body)
        assert payload["response_format"]["type"] == "json_schema"
        records = json.loads(payload["messages"][1]["content"])
        assert records["manufacturing_order"] == ORDER
        assert records["business_results"]["potential_delay_operations"] == ["0099"]
        assert [r["operation_id"] for r in records["business_results"]["operations"]] == [
            "0099",
            "0100",
        ]
        with lock:
            state["inference_calls"] += 1
            mode = state["inference"]
        if mode == "refuse":
            return self.reply(503, {"error": "synthetic-inference-canary"})
        with httpx.Client(timeout=26, trust_env=False, follow_redirects=False) as client:
            response = client.post("http://127.0.0.1:8080/v1/chat/completions", json=payload)
            response.raise_for_status()
            answer = response.json()
        with lock:
            state["qwen_calls"] += 1
        self.reply(200, answer)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
fixture_port, bridge_port = server.server_port, free_port()
env = {
    **os.environ,
    "MODEL_NAME": "qwen2.5:1.5b",
    "MODEL_GATEWAY_TOKEN": "synthetic-bridge-token",
    "MODEL_GATEWAY_HOST": "127.0.0.1",
    "MODEL_GATEWAY_PORT": str(bridge_port),
    "AICORE_TOKEN_URL": f"http://127.0.0.1:{fixture_port}/oauth/token",
    "AICORE_CUSTOM_DEPLOYMENT_URL": f"http://127.0.0.1:{fixture_port}",
    "AICORE_CLIENT_ID": "synthetic-client",
    "AICORE_CLIENT_SECRET": "synthetic-secret",
    "AICORE_RESOURCE_GROUP": "cookbook-test",
    "AICORE_CUSTOM_TIMEOUT_SECONDS": "25",
}
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
signal.signal(signal.SIGINT, lambda *_: stop.set())
process = None
try:
    process = subprocess.Popen(
        [sys.executable, "-m", "production_order_agent.model_bridge"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with httpx.Client(timeout=0.5, trust_env=False) as client:
        for _ in range(100):
            assert process.poll() is None
            try:
                if client.get(f"http://127.0.0.1:{bridge_port}/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("Bridge startup failed")
    print(
        "READY "
        + json.dumps(
            {
                "fixture_url": f"http://127.0.0.1:{fixture_port}",
                "bridge_url": f"http://127.0.0.1:{bridge_port}/v1",
            }
        ),
        flush=True,
    )
    while not stop.wait(0.5):
        assert process.poll() is None
finally:
    if process is not None:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(10)
    server.shutdown()
    server.server_close()
    thread.join(5)
    assert not thread.is_alive()
    for port in [fixture_port, bridge_port]:
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", port)) != 0
    print(
        "CLEANUP "
        + json.dumps(
            {
                "bridge_reaped": process is None or process.poll() is not None,
                "fixture_and_bridge_ports_closed": True,
            }
        ),
        flush=True,
    )
