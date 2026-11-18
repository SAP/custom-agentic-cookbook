"""Real local A2A/MCP processes over synthetic OAuth/OData, never a tenant."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

SAMPLE = Path(__file__).resolve().parents[1]


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stopped_port(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.parametrize("shape", ["A", "B"])
def test_cross_process_business_failure_recovery_and_cleanup(tmp_path, shape):
    observations = []
    state = {"code": 200}

    class Backend(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, code, value):
            body = json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            assert self.path == "/token"
            self.respond(200, {"access_token": "fixture-token", "expires_in": 60})

        def do_GET(self):
            parts = urlsplit(self.path)
            if shape == "B" and parts.path.rstrip("/") == "/relational/SPACE/SALES":
                self.respond(200, {"value": [{"name": "Rows", "url": "Rows"}]})
                return
            query = parse_qs(parts.query)
            assert parts.path in {"/SPACE/SALES", "/relational/SPACE/SALES/Rows"}
            assert query["$select"] == ["Region,Revenue"]
            assert query["$filter"] == ["Region eq 'EMEA'"]
            assert query["$top"] == ["50"]
            observations.append(state["code"])
            self.respond(
                state["code"],
                {
                    "value": [
                        {
                            "Region": "EMEA",
                            "Revenue": "12.50",
                            "PrivateExtra": "private-record-marker",
                        },
                        {"Region": "EMEA", "Revenue": "7.50"},
                    ]
                },
            )

    backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
    backend_thread.start()
    backend_url = f"http://127.0.0.1:{backend.server_port}"
    mcp_port, agent_port = unused_port(), unused_port()
    env = {
        **os.environ,
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": str(mcp_port),
        "MCP_SERVER_URL": f"http://127.0.0.1:{mcp_port}/sse",
        "PORT": str(agent_port),
        "URL": f"http://127.0.0.1:{agent_port}",
        "A2A_SOURCE_MODE": "fixture",
        "BDC_ODATA_BASE_URL": backend_url + ("/SPACE" if shape == "A" else "/relational"),
        "BDC_TOKEN_URL": backend_url + "/token",
        "BDC_SPACE": "SPACE",
        "BDC_VIEW": "SALES",
        "BDC_SHAPE": shape,
        "BDC_CLIENT_ID": "fixture-id",
        "BDC_CLIENT_SECRET": "fixture-secret",
    }
    # This test-only process wrapper permits HTTP solely for the synthetic loopback
    # fixture. The advertised MCP entrypoint's HTTPS-only default is unchanged.
    wrapper = (
        "import mcp_server; from datasphere import DatasphereReader; "
        "mcp_server.DatasphereReader=lambda **kw: DatasphereReader(**kw,allow_http=True); "
        "mcp_server.mcp.run(transport='sse')"
    )
    children, handles = [], []
    receipt = {
        "shape": shape,
        "source": "synthetic OAuth/OData fixture; no tenant proof",
        "http_only_test_wrapper": True,
        "business": [],
        "cleanup": {},
    }
    try:
        assert mcp_port != agent_port and stopped_port(mcp_port) and stopped_port(agent_port)
        for name, command, port in [
            ("mcp", [sys.executable, "-c", wrapper], mcp_port),
            ("a2a", [sys.executable, "a2a_server.py"], agent_port),
        ]:
            log = (tmp_path / (name + ".log")).open("w+")
            handles.append(log)
            process = subprocess.Popen(command, cwd=SAMPLE, env=env, stdout=log, stderr=log)
            children.append((name, process, port))
            deadline = time.monotonic() + 10
            while stopped_port(port):
                assert process.poll() is None, f"owned {name} process exited before startup"
                assert time.monotonic() < deadline, f"owned {name} process startup timeout"
                time.sleep(0.02)
        with httpx.Client(base_url=env["URL"], trust_env=False, timeout=15) as client:
            card = client.get("/.well-known/agent-card.json").json()
            assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
            for code, expected in [
                (200, "TASK_STATE_COMPLETED"),
                (403, "TASK_STATE_FAILED"),
                (200, "TASK_STATE_COMPLETED"),
            ]:
                state["code"] = code
                body = {
                    "jsonrpc": "2.0",
                    "id": str(code),
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": f"fixture-{len(receipt['business'])}",
                            "role": "ROLE_USER",
                            "parts": [{"text": "revenue EMEA"}],
                        }
                    },
                }
                response = client.post("/", headers={"A2A-Version": "1.0"}, json=body)
                assert response.status_code == 200
                reply = response.json()["result"]["task"]
                assert reply["status"]["state"] == expected
                text = reply["artifacts"][0]["parts"][0]["text"]
                assert not any(
                    marker in text
                    for marker in [
                        "fixture-secret",
                        "fixture-token",
                        "private-record-marker",
                        backend_url,
                    ]
                )
                if code == 200:
                    answer = json.loads(text)
                    assert answer == {
                        "region": "EMEA",
                        "row_count": 2,
                        "revenue": "20.00",
                        "limit": 50,
                        "bounded": True,
                        "source": receipt["source"],
                    }
                    receipt["business"].append({"state": expected, "answer": answer})
                else:
                    assert "could not be retrieved" in text
                    receipt["business"].append({"state": expected, "safe_failure": True})
        assert observations == [200, 403, 200]
    finally:
        for name, process, port in reversed(children):
            process.terminate()  # Only this fixture's Popen-owned process, never a discovered PID.
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(5)
            receipt["cleanup"][name] = {
                "owned_pid": process.pid,
                "exit_code": process.returncode,
                "process_absent": process.poll() is not None,
                "port_closed": stopped_port(port),
            }
        backend.shutdown()
        backend.server_close()
        backend_thread.join(5)
        receipt["cleanup"]["backend"] = {
            "thread_absent": not backend_thread.is_alive(),
            "port_closed": stopped_port(backend.server_port),
        }
        for log in handles:
            log.seek(0)
            output = log.read()
            log.close()
            assert not any(
                marker in output
                for marker in [
                    "fixture-secret",
                    "fixture-token",
                    "private-record-marker",
                    backend_url,
                ]
            )
    assert all(item["port_closed"] for item in receipt["cleanup"].values())
    assert all(
        item["process_absent"] for name, item in receipt["cleanup"].items() if name != "backend"
    )
    assert receipt["cleanup"]["backend"]["thread_absent"]
    if directory := os.getenv("COOKBOOK_FIXTURE_RECEIPTS"):
        Path(directory, f"shape-{shape}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
