"""Exercise a real A2A and MCP flow through a controlled private model gateway."""

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

from production_order_agent.agent import deterministic_summary
from production_order_agent.custom_model import _url, business_results
from production_order_agent.mcp_server import MOCK_ORDERS


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(model_url=None):
    expected = MOCK_ORDERS["1000000"]
    seen = []
    model_replies = []
    os.environ["MODEL_SMOKE_URL"] = model_url or ""
    upstream = _url("MODEL_SMOKE_URL") + "/chat/completions"

    class Gateway(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.path == "/oauth/token":
                    payload = {
                        "access_token": "synthetic-token",
                        "token_type": "Bearer",
                        "expires_in": 60,
                    }
                else:
                    assert self.path == "/v1/chat/completions"
                    request = json.loads(body)
                    records = json.loads(request["messages"][1]["content"])
                    assert records["business_results"] == business_results(
                        expected["status"], expected["operations"]
                    )
                    assert records["manufacturing_order"] == "1000000"
                    seen.append(request["model"])
                    if upstream:
                        with httpx.Client(
                            timeout=310, trust_env=False, follow_redirects=False
                        ) as client:
                            response = client.post(
                                upstream,
                                json=request,
                                headers={"Authorization": "Bearer synthetic-token"},
                            )
                            response.raise_for_status()
                            payload = response.json()
                    else:
                        reply = deterministic_summary(
                            "1000000", expected["status"], expected["operations"]
                        )
                        payload = {
                            "choices": [{"message": {"role": "assistant", "content": reply}}]
                        }
                    model_replies.append(payload["choices"][0]["message"]["content"])
                encoded = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception:
                self.send_error(502, "Controlled gateway failed")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    gateway_port = server.server_port
    agent_port, mcp_port = free_port(), free_port()
    processes = []
    environment = os.environ.copy()
    environment.update(
        DATA_MODE="mock",
        MCP_HOST="127.0.0.1",
        MCP_PORT=str(mcp_port),
        HOST="127.0.0.1",
        PORT=str(agent_port),
        URL=f"http://127.0.0.1:{agent_port}",
        MCP_SERVER_URL=f"http://127.0.0.1:{mcp_port}/sse",
        LLM_PROVIDER="aicore-custom",
        MODEL_NAME="qwen2.5:1.5b" if upstream else "fixture-model",
        AICORE_CUSTOM_DEPLOYMENT_URL=f"http://127.0.0.1:{gateway_port}",
        AICORE_TOKEN_URL=f"http://127.0.0.1:{gateway_port}/oauth/token",
        AICORE_CLIENT_ID="synthetic-client",
        AICORE_CLIENT_SECRET="synthetic-key",
        AICORE_RESOURCE_GROUP="cookbook-test",
        AICORE_CUSTOM_TIMEOUT_SECONDS="300",
    )
    try:
        for module in ("production_order_agent.mcp_server", "production_order_agent"):
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-m", module],
                    env=environment,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        with httpx.Client(timeout=310, trust_env=False) as client:
            for _ in range(100):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("Owned sample process exited during startup")
                try:
                    response = client.get(
                        f"http://127.0.0.1:{agent_port}/.well-known/agent-card.json"
                    )
                    if response.status_code == 200:
                        with socket.socket() as probe:
                            if probe.connect_ex(("127.0.0.1", mcp_port)) == 0:
                                break
                except httpx.RequestError:
                    pass
                time.sleep(0.1)
            response = client.post(
                f"http://127.0.0.1:{agent_port}/",
                headers={"A2A-Version": "1.0"},
                json={
                    "jsonrpc": "2.0",
                    "id": "gateway-smoke",
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": "gateway-smoke",
                            "role": "ROLE_USER",
                            "parts": [{"text": "Why is order 1000000 delayed?"}],
                        }
                    },
                },
            )
            response.raise_for_status()
            task = response.json()["result"]["task"]
            assert task["status"]["state"] == "TASK_STATE_COMPLETED"
            reply = "".join(
                part.get("text", "") for artifact in task["artifacts"] for part in artifact["parts"]
            )
            assert seen == [environment["MODEL_NAME"]]
            assert reply.strip() == model_replies[0].strip()
            assert all(
                text.lower() in reply.lower()
                for text in ["Released", "Partially Confirmed", "0010", "0020", "delay"]
            ), reply
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
    for port in (agent_port, mcp_port, gateway_port):
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", port)) != 0
    return {
        "completed_a2a": True,
        "backend_records_match": True,
        "model_reply_matches_artifact": True,
        "owned_processes_reaped": True,
        "owned_ports_closed": True,
        "scope": "Actual local model" if upstream else "Controlled gateway fixture",
        "reply": reply,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-url", required=True, help="Approved loopback model base URL including /v1"
    )
    args = parser.parse_args()
    print(json.dumps(run(args.model_url), indent=2))
