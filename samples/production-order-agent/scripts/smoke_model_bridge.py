"""Run the private bridge through controlled OAuth and actual local Qwen inference."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from production_order_agent.custom_model import _url, business_results
from production_order_agent.mcp_server import MOCK_ORDERS


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(model_url):
    os.environ["MODEL_BRIDGE_SMOKE_URL"] = model_url
    upstream = _url("MODEL_BRIDGE_SMOKE_URL") + "/chat/completions"
    expected = MOCK_ORDERS["1000000"]
    replies = []
    oauth_calls = []

    class Relay(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.path == "/oauth/token":
                    assert self.headers.get("Authorization", "").startswith("Basic ")
                    oauth_calls.append(True)
                    payload = {
                        "access_token": "synthetic-oauth-token",
                        "token_type": "Bearer",
                        "expires_in": 60,
                    }
                else:
                    assert self.path == "/v1/chat/completions"
                    assert self.headers["Authorization"] == "Bearer synthetic-oauth-token"
                    request = json.loads(body)
                    assert b"caller-prompt-canary" not in body
                    assert b"synthetic-bridge-token" not in body
                    records = json.loads(request["messages"][1]["content"])
                    assert records["business_results"] == business_results(
                        expected["status"], expected["operations"]
                    )
                    with httpx.Client(
                        timeout=305, follow_redirects=False, trust_env=False
                    ) as client:
                        response = client.post(upstream, json=request)
                        response.raise_for_status()
                        payload = response.json()
                    replies.append(payload["choices"][0]["message"]["content"])
                encoded = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(encoded)
            except Exception:
                self.send_error(502, "Controlled relay failed")

    relay = ThreadingHTTPServer(("127.0.0.1", 0), Relay)
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    relay_port = relay.server_port
    bridge_port = free_port()
    environment = os.environ.copy()
    environment.update(
        MODEL_NAME="qwen2.5:1.5b",
        MODEL_GATEWAY_TOKEN="synthetic-bridge-token",
        MODEL_GATEWAY_HOST="127.0.0.1",
        MODEL_GATEWAY_PORT=str(bridge_port),
        AICORE_TOKEN_URL=f"http://127.0.0.1:{relay_port}/oauth/token",
        AICORE_CUSTOM_DEPLOYMENT_URL=f"http://127.0.0.1:{relay_port}",
        AICORE_CLIENT_ID="synthetic-client",
        AICORE_CLIENT_SECRET="synthetic-secret",
        AICORE_RESOURCE_GROUP="cookbook-test",
        AICORE_CUSTOM_TIMEOUT_SECONDS="300",
    )
    process = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "production_order_agent.model_bridge"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with httpx.Client(timeout=310, trust_env=False) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Owned bridge exited during startup")
                try:
                    if client.get(f"http://127.0.0.1:{bridge_port}/healthz").status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                time.sleep(0.1)
            response = client.post(
                f"http://127.0.0.1:{bridge_port}/v1/chat/completions",
                headers={"Authorization": "Bearer synthetic-bridge-token"},
                json={
                    "model": "qwen2.5:1.5b",
                    "max_tokens": 2048,
                    "messages": [
                        {"role": "system", "content": "caller-prompt-canary"},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "manufacturing_order": "1000000",
                                    "statuses": expected["status"],
                                    "operations": expected["operations"],
                                }
                            ),
                        },
                    ],
                },
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            assert oauth_calls == [True]
            assert replies == [answer]
            assert response.headers["Connection"] == "close"
            assert json.loads(answer)["potential_delay_operations"] == ["0020"]
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        relay.shutdown()
        relay.server_close()
        thread.join(timeout=10)
    for port in (bridge_port, relay_port):
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", port)) != 0
    return {
        "bridge_completion": True,
        "actual_model_reply_matches": True,
        "caller_prompts_and_bearer_token_absent_upstream": True,
        "oauth_exchange": "controlled fixture",
        "owned_process_reaped": True,
        "owned_ports_closed": True,
        "reply": answer,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-url", required=True, help="Approved loopback model URL including /v1"
    )
    print(json.dumps(run(parser.parse_args().model_url), indent=2))
