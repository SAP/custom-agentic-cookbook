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
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import httpx
import pytest
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
    started = threading.Event()
    release = threading.Event()
    behavior = "normal"
    paths = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        type(self).paths.append(self.path)
        assert self.headers.get("APIKey") == "synthetic-key"
        if type(self).behavior == "slow":
            type(self).started.set()
            type(self).release.wait(5)
        status = 503 if type(self).behavior == "failure" else 200
        data = STATUSES if "to_ProductionOrderStatus" in self.path else OPERATIONS
        body = json.dumps({"d": {"results": data}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with suppress(BrokenPipeError):
            self.wfile.write(body)


@contextmanager
def runtime():
    Fixture.behavior = "normal"
    Fixture.paths = []
    Fixture.started.clear()
    Fixture.release.clear()
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
        "S4_REQUEST_TIMEOUT_SECONDS": "0.8",
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
        yield env
    finally:
        Fixture.release.set()
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
        assert all(proc.poll() is not None for proc in processes)
        for used in [mcp_port, agent_port]:
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


@pytest.mark.parametrize("behavior", ["slow", "failure"])
def test_timeout_and_backend_failure_produce_failed_a2a_tasks(behavior):
    with runtime() as env:
        Fixture.behavior = behavior
        task = send_message(env)
        assert task["status"]["state"] == "TASK_STATE_FAILED"
        result = json.dumps(task)
        assert "synthetic-key" not in result
        assert "/service" not in result
        assert "Fixture Released" not in result


async def test_discovery_completes_while_http_fetch_is_blocked():
    with runtime() as env:
        Fixture.behavior = "slow"
        async with sse_client(env["MCP_SERVER_URL"]) as streams, ClientSession(*streams) as session:
            await session.initialize()
            request = asyncio.create_task(
                session.call_tool("get_production_order_status", {"manufacturing_order": ORDER})
            )
            try:
                async with asyncio.timeout(3):
                    while not Fixture.started.is_set():
                        await asyncio.sleep(0.01)
                    tools = await asyncio.wait_for(session.list_tools(), 0.5)
                    assert len(tools.tools) == 2
                    assert not request.done()
            finally:
                Fixture.release.set()
            assert not (await request).isError
