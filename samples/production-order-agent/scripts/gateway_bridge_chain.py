import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client

parser = argparse.ArgumentParser()
parser.add_argument("--fixture-url", required=True)
parser.add_argument("--bridge-url", required=True)
args = parser.parse_args()
ORDER = "7654321"
expected = {
    "status_names": ["Fixture Released"],
    "operations": [
        {"operation_id": "0099", "confirmation": "not finally confirmed"},
        {"operation_id": "0100", "confirmation": "confirmed"},
    ],
    "potential_delay_operations": ["0099"],
}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def mcp_ready(url):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            async with asyncio.timeout(1):
                async with sse_client(url) as streams, ClientSession(*streams) as session:
                    await session.initialize()
                    names = {t.name for t in (await session.list_tools()).tools}
                    assert names == {
                        "get_production_order_status",
                        "get_production_order_operations",
                    }
                    return
        except Exception:
            await asyncio.sleep(0.05)
    raise RuntimeError("Owned MCP did not become ready")


mcp_port, agent_port = free_port(), free_port()
base = f"http://127.0.0.1:{agent_port}"
environment = {
    **os.environ,
    "DATA_MODE": "s4",
    "S4_BASE_URL": args.fixture_url + "/service",
    "S4_API_KEY": "synthetic-fixture-key",
    "MCP_HOST": "127.0.0.1",
    "MCP_PORT": str(mcp_port),
    "HOST": "127.0.0.1",
    "PORT": str(agent_port),
    "URL": base,
    "MCP_SERVER_URL": f"http://127.0.0.1:{mcp_port}/sse",
    "LLM_PROVIDER": "openai-compatible",
    "MODEL_NAME": "qwen2.5:1.5b",
    "MODEL_GATEWAY_URL": args.bridge_url,
    "MODEL_GATEWAY_API_KEY": "synthetic-bridge-token",
}
processes = []
results = []


def control(client, **updates):
    client.post(
        args.fixture_url + "/control",
        json=updates,
        headers={"Authorization": "Bearer synthetic-control-token"},
    ).raise_for_status()


def state(client):
    response = client.get(args.fixture_url + "/state")
    response.raise_for_status()
    return response.json()


def message(client):
    started = time.monotonic()
    response = client.post(
        base + "/",
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
    elapsed = time.monotonic() - started
    assert elapsed < 30, elapsed
    return response.json()["result"]["task"], elapsed


def success(client, label):
    before = state(client)
    task, elapsed = message(client)
    assert task["status"]["state"] == "TASK_STATE_COMPLETED", task
    text = "".join(part.get("text", "") for a in task["artifacts"] for part in a["parts"])
    assert json.loads(text) == expected, text
    after = state(client)
    assert after["data_calls"] == before["data_calls"] + 2
    assert after["qwen_calls"] == before["qwen_calls"] + 1
    assert after["oauth_calls"] == before["oauth_calls"] + 1
    result = {
        "phase": label,
        "completed_a2a": True,
        "backend_business_match": True,
        "actual_qwen_inference": True,
        "elapsed_seconds": round(elapsed, 3),
    }
    results.append(result)
    print(json.dumps(result), flush=True)


def failure(client, label, blocked):
    before = state(client)
    task, elapsed = message(client)
    assert task["status"]["state"] == "TASK_STATE_FAILED", task
    text = json.dumps(task)
    for marker in [
        "synthetic-fixture-key",
        "synthetic-bridge-token",
        "synthetic-oauth-token",
        "synthetic-response-canary",
        "synthetic-inference-canary",
        "synthetic-oauth-canary",
        "127.0.0.1",
        "Fixture Released",
        "0099",
    ]:
        assert marker not in text, marker
    after = state(client)
    assert after["qwen_calls"] == before["qwen_calls"]
    if blocked == "data":
        assert after["oauth_calls"] == before["oauth_calls"]
        assert after["inference_calls"] == before["inference_calls"]
    if blocked == "oauth":
        assert after["inference_calls"] == before["inference_calls"]
    result = {
        "phase": label,
        "failed_a2a": True,
        "safe_diagnostic": True,
        "no_mock_fallback": True,
        "qwen_not_called": True,
        "elapsed_seconds": round(elapsed, 3),
    }
    results.append(result)
    print(json.dumps(result), flush=True)


try:
    for module in ["production_order_agent.mcp_server", "production_order_agent"]:
        processes.append(
            subprocess.Popen(
                [sys.executable, "-m", module],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
    asyncio.run(mcp_ready(environment["MCP_SERVER_URL"]))
    with httpx.Client(timeout=35, trust_env=False, follow_redirects=False) as client:
        for _ in range(100):
            assert all(p.poll() is None for p in processes)
            try:
                if client.get(base + "/.well-known/agent-card.json").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("Owned agent did not become ready")
        for encoding in ["gzip", "deflate"]:
            control(client, encoding=encoding, data="ok", oauth="ok", inference="ok")
            success(client, encoding + "-business")
        for boundary in ["data", "oauth", "inference"]:
            control(client, **{boundary: "refuse"})
            failure(client, boundary + "-refusal", boundary)
            control(client, **{boundary: "ok"})
            success(client, boundary + "-same-agent-recovery")
        assert all(p.poll() is None for p in processes)
finally:
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(10)
    assert all(p.poll() is not None for p in processes)
    for port in [agent_port, mcp_port]:
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", port)) != 0
    print(
        "SUMMARY "
        + json.dumps(
            {
                "phases": results,
                "same_agent_pids_preserved": True,
                "owned_processes_reaped": True,
                "owned_agent_mcp_ports_closed": True,
            }
        ),
        flush=True,
    )
