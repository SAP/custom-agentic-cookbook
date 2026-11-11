"""Loopback integration: HTTP fixture -> MCP -> A2A artifacts and discovery under load."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client

ORDER = "7654321"
STATUSES = [{"ManufacturingOrder": ORDER, "StatusCode": "FIX1", "StatusName": "Fixture Released"}]
OPERATIONS = [
    {
        "ManufacturingOrder": ORDER,
        "ManufacturingOrderOperation": "9876",
        "MfgOrderOperationText": "Fixture inspection",
        "WorkCenter": "FIXTURE-WC",
        "OpErlstSchedldExecEndDte": "2001-01-01",
        "OperationIsFinallyConfirmed": False,
    }
]


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Fixture(BaseHTTPRequestHandler):
    behavior = "normal"
    paths = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        type(self).paths.append(self.path)
        assert self.headers.get("APIKey") == "synthetic-key"
        status = 503 if type(self).behavior == "failure" else 200
        data = STATUSES if "to_ProductionOrderStatus" in self.path else OPERATIONS
        body = json.dumps({"d": {"results": data}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with suppress(BrokenPipeError):
            self.wfile.write(body)


async def wait_for_mcp(url, deadline):
    while time.monotonic() < deadline:
        try:
            async with asyncio.timeout(min(1, deadline - time.monotonic())):
                async with sse_client(url) as streams, ClientSession(*streams) as session:
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if names != {"get_production_order_status", "get_production_order_operations"}:
            raise RuntimeError("sample MCP tools were not discovered")
        return
    raise RuntimeError("sample MCP startup timed out")


@contextmanager
def runtime():
    Fixture.behavior = "normal"
    Fixture.paths = []
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    worker = threading.Thread(target=fixture.serve_forever, daemon=True)
    worker.start()
    mcp_port, agent_port = port(), port()
    env = {
        **os.environ,
        "DATA_MODE": "s4",
        "LLM_PROVIDER": "mock",
        "S4_API_KEY": "synthetic-key",
        "S4_BASE_URL": f"http://127.0.0.1:{fixture.server_port}/service",
        "MCP_PORT": str(mcp_port),
        "MCP_HOST": "127.0.0.1",
        "PORT": str(agent_port),
        "HOST": "127.0.0.1",
        "URL": f"http://127.0.0.1:{agent_port}",
        "MCP_SERVER_URL": f"http://127.0.0.1:{mcp_port}/sse",
    }
    processes = []
    try:
        for module in ["production_order_agent.mcp_server", "production_order_agent"]:
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-m", module],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        deadline = time.monotonic() + 15
        with httpx.Client(timeout=0.5, trust_env=False) as client:
            while time.monotonic() < deadline:
                if any(proc.poll() is not None for proc in processes):
                    raise RuntimeError("sample child process exited before startup")
                try:
                    if client.get(env["URL"] + "/.well-known/agent-card.json").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
            else:
                raise RuntimeError("sample startup timed out")
        # Keep this synchronous fixture safe when called from an async test.
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, wait_for_mcp(env["MCP_SERVER_URL"], deadline)).result()
        yield env
    finally:
        for proc in processes:
            proc.terminate()
        for proc in processes:
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)
        fixture.shutdown()
        fixture.server_close()
        worker.join(5)
        assert not worker.is_alive()
        assert all(proc.poll() is not None for proc in processes)
        for used in [fixture.server_port, mcp_port, agent_port]:
            with socket.socket() as sock:
                assert sock.connect_ex(("127.0.0.1", used)) != 0


def send_message(env):
    with httpx.Client(timeout=8, trust_env=False) as client:
        response = client.post(
            env["URL"] + "/",
            headers={"A2A-Version": "1.0"},
            json={
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": str(uuid4()),
                        "role": "ROLE_USER",
                        "parts": [{"text": f"Why is production order {ORDER} delayed?"}],
                    }
                },
            },
        )
        response.raise_for_status()
        return response.json()["result"]["task"]


def test_runtime_waits_for_mcp_when_agent_card_is_already_ready(monkeypatch, tmp_path):
    gate = tmp_path / "start-mcp"
    card_ready = threading.Event()
    runtime_ready = threading.Event()
    finish = threading.Event()
    errors = []
    original_popen = subprocess.Popen
    original_get = httpx.Client.get

    def delayed_mcp(command, **kwargs):
        if command[-1] == "production_order_agent.mcp_server":
            script = (
                "import pathlib, runpy, time\n"
                f"gate = pathlib.Path({str(gate)!r})\n"
                "while not gate.exists():\n"
                "    time.sleep(0.01)\n"
                "runpy.run_module('production_order_agent.mcp_server', run_name='__main__')\n"
            )
            command = [sys.executable, "-c", script]
        return original_popen(command, **kwargs)

    def observe_card(client, url, **kwargs):
        response = original_get(client, url, **kwargs)
        if url.endswith("/.well-known/agent-card.json") and response.status_code == 200:
            card_ready.set()
        return response

    def start_runtime():
        try:
            with runtime():
                runtime_ready.set()
                finish.wait(15)
        except Exception as error:
            errors.append(error)

    monkeypatch.setattr(subprocess, "Popen", delayed_mcp)
    monkeypatch.setattr(httpx.Client, "get", observe_card)
    worker = threading.Thread(target=start_runtime)
    worker.start()
    try:
        assert card_ready.wait(10)
        assert not runtime_ready.wait(0.2), "Agent Card alone must not release the runtime"
        gate.touch()
        assert runtime_ready.wait(10)
        assert not Fixture.paths
    finally:
        gate.touch()
        finish.set()
        worker.join(20)
    assert not worker.is_alive()
    assert not errors


def test_fixture_records_reach_completed_a2a_artifact():
    with runtime() as env:
        task = send_message(env)
        assert task["status"]["state"] == "TASK_STATE_COMPLETED"
        answer = chr(10).join(
            part["text"] for artifact in task["artifacts"] for part in artifact["parts"]
        )
        for expected in [
            ORDER,
            "FIX1",
            "Fixture Released",
            "9876",
            "Fixture inspection",
            "FIXTURE-WC",
            "2001-01-01",
            "Potential delay",
        ]:
            assert expected in answer
        for forbidden in ["1000000", "0010", "0020", "ASSEMBLY-01", "Partially Confirmed"]:
            assert forbidden not in answer
        assert len(Fixture.paths) == 2
        assert all(f"A_ProductionOrder_2('{ORDER}')" in path for path in Fixture.paths)


def test_backend_failure_produces_safe_failed_task_and_recovers():
    with runtime() as env:
        Fixture.behavior = "failure"
        task = send_message(env)
        assert any(f"A_ProductionOrder_2('{ORDER}')" in path for path in Fixture.paths)
        assert task["status"]["state"] == "TASK_STATE_FAILED"
        result = json.dumps(task)
        assert "synthetic-key" not in result
        assert "/service" not in result
        assert "Fixture Released" not in result
        Fixture.behavior = "normal"
        recovered = send_message(env)
        assert recovered["status"]["state"] == "TASK_STATE_COMPLETED"
        answer = json.dumps(recovered["artifacts"])
        assert "Fixture Released" in answer
        assert "Fixture inspection" in answer
        assert "Partially Confirmed" not in answer


def test_documented_data_smoke_compares_http_records_and_recovers():
    with runtime() as env:
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "smoke_data.py"),
            "--base-url",
            env["URL"],
            "--order-id",
            ORDER,
        ]
        for behavior in ["normal", "failure", "normal"]:
            Fixture.behavior = behavior
            process = subprocess.run(
                command, env=env, capture_output=True, text=True, timeout=15, check=False
            )
            if behavior == "failure":
                assert process.returncode == 1
                assert process.stdout == ""
                assert "Data smoke failed (RuntimeError)" in process.stderr
            else:
                assert process.returncode == 0
                assert json.loads(process.stdout) == {
                    "status_records": 1,
                    "operation_records": 1,
                    "state": "TASK_STATE_COMPLETED",
                    "reply_matches_backend": True,
                }
                assert process.stderr == ""
            for marker in ["synthetic-key", "/service", "Fixture Released", "Fixture inspection"]:
                assert marker not in process.stdout + process.stderr
