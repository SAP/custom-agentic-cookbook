"""Real loopback A2A-to-MCP path with explicit fixture data and exact process cleanup."""

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def runtime(backend="fixture"):
    mcp_port, agent_port = port(), port()
    env = {
        **os.environ,
        "RETRIEVAL_BACKEND": backend,
        "MCP_PORT": str(mcp_port),
        "MCP_HOST": "127.0.0.1",
        "MCP_SERVER_URL": f"http://127.0.0.1:{mcp_port}/sse",
        "URL": f"http://127.0.0.1:{agent_port}",
        "PORT": str(agent_port),
        "HOST": "127.0.0.1",
    }
    processes = []
    try:
        for module in ["hana_retrieval.mcp_server", "hana_retrieval"]:
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
                assert not any(proc.poll() is not None for proc in processes)
                try:
                    if client.get(env["URL"] + "/.well-known/agent-card.json").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
            else:
                raise RuntimeError("sample startup timed out")
        yield env["URL"]
    finally:
        for proc in processes:
            proc.terminate()
        for proc in processes:
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)
        assert all(proc.poll() is not None for proc in processes)
        for used in [mcp_port, agent_port]:
            with socket.socket() as sock:
                assert sock.connect_ex(("127.0.0.1", used)) != 0


def send(url, question):
    with httpx.Client(timeout=8, trust_env=False) as client:
        response = client.post(
            url + "/",
            headers={"A2A-Version": "1.0"},
            json={
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": str(uuid4()),
                        "role": "ROLE_USER",
                        "parts": [{"text": question}],
                    }
                },
            },
        )
    response.raise_for_status()
    task = response.json()["result"]["task"]
    return task["status"]["state"], "\n".join(
        part["text"] for item in task["artifacts"] for part in item["parts"]
    )


def test_vector_and_graph_sources_reach_a2a_reply():
    with runtime() as url:
        state, vector = send(url, "vector:manufacturing:assembly delay")
        assert state == "TASK_STATE_COMPLETED"
        assert "unconfirmed assembly" in vector
        assert "https://example.com/source/doc-1" in vector
        assert "revenue report" not in vector
        state, graph = send(url, "graph:customer-42")
        assert state == "TASK_STATE_COMPLETED"
        assert "contact-7" in graph
        assert "https://example.com/source/customer-42" in graph
        state, empty = send(url, "graph:missing")
        assert state == "TASK_STATE_COMPLETED"
        assert "No matching source" in empty


@pytest.mark.parametrize("question", ["graph:../escape", "vector:manufacturing:" + "x" * 2001])
def test_malformed_tool_inputs_fail_without_raw_errors(question):
    with runtime() as url:
        state, answer = send(url, question)
        assert state == "TASK_STATE_FAILED"
        assert "Traceback" not in answer


def test_invalid_backend_never_falls_back_to_fixture():
    with runtime("unsupported") as url:
        state, answer = send(url, "graph:customer-42")
        assert state == "TASK_STATE_FAILED"
        assert "contact-7" not in answer
