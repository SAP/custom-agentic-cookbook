from __future__ import annotations

import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

from production_order_agent import mcp_server
from production_order_agent.__main__ import create_app
from production_order_agent.agent import ProductionOrderAgent
from production_order_agent.settings import Settings

ORDER = "7654321"
TOOLS = {
    "get_production_order_status": ("to_ProductionOrderStatus", {"StatusName": "Created"}),
    "get_production_order_operations": (
        "to_ProductionOrderOperation",
        {"ManufacturingOrderOperation": "0030"},
    ),
}


@pytest.fixture
def s4_backend(monkeypatch: pytest.MonkeyPatch) -> dict:
    state = {"requests": [], "status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        record = next(record for nav, record in TOOLS.values() if nav in request.url.path)
        return httpx.Response(state["status"], json={"d": {"results": [record]}})

    real_client = httpx.Client

    def client(*args, **kwargs) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(handler)
        kwargs["trust_env"] = False
        return real_client(*args, **kwargs)

    monkeypatch.setenv("DATA_MODE", "s4")
    monkeypatch.setenv("S4_BASE_URL", "https://backend.example.invalid/service")
    monkeypatch.setenv("S4_API_KEY", "synthetic-key")
    monkeypatch.setattr(httpx, "Client", client)
    return state


@pytest.mark.parametrize("tool", TOOLS)
async def test_s4_mode_through_registered_tools(s4_backend: dict, tool: str) -> None:
    result = await mcp_server.mcp.call_tool(tool, {"manufacturing_order": ORDER})
    navigation, record = TOOLS[tool]
    assert result[1]["result"] == [record]
    request = s4_backend["requests"][0]
    assert request.method == "GET"
    assert str(request.url) == (
        f"https://backend.example.invalid/service/"
        f"A_ProductionOrder_2('{ORDER}')/{navigation}?$format=json"
    )
    assert request.headers["APIKey"] == "synthetic-key"


@pytest.mark.parametrize("tool", TOOLS)
async def test_missing_key_stops_registered_tool_before_network(
    s4_backend: dict, monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    monkeypatch.delenv("S4_API_KEY")
    with pytest.raises(ToolError, match="S4_API_KEY is required"):
        await mcp_server.mcp.call_tool(tool, {"manufacturing_order": ORDER})
    assert s4_backend["requests"] == []


def test_s4_failure_produces_safe_failed_a2a_task(s4_backend: dict) -> None:
    s4_backend["status"] = 503

    async def tool_caller(_: str, tool: str, order: str) -> list[dict]:
        result = await mcp_server.mcp.call_tool(tool, {"manufacturing_order": order})
        return result[1]["result"]

    agent = ProductionOrderAgent(Settings(llm_provider="mock"), tool_caller=tool_caller)
    with TestClient(create_app(agent=agent)) as client:
        response = client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json={
                "jsonrpc": "2.0",
                "id": "s4-failure",
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": "s4-failure-message",
                        "role": "ROLE_USER",
                        "parts": [{"text": f"Show order {ORDER}"}],
                    }
                },
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
    serialized = json.dumps(payload)
    assert "could not be retrieved" in serialized
    assert "synthetic-key" not in serialized
    assert "backend.example.invalid" not in serialized
    assert s4_backend["requests"]
