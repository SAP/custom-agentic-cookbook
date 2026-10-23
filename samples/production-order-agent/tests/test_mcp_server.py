from __future__ import annotations

import asyncio
import threading
from typing import Any

import httpx
import pytest

from production_order_agent import mcp_server


@pytest.mark.parametrize(
    "manufacturing_order",
    ["", " ", "ABC123", "123-456", "１２３", "1" * 21],
)
def test_validate_order_id_rejects_invalid_values(manufacturing_order: str) -> None:
    with pytest.raises(ValueError, match="manufacturing_order"):
        mcp_server.validate_order_id(manufacturing_order)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"value": [{"StatusCode": "I0002"}]}, [{"StatusCode": "I0002"}]),
        ({"d": {"results": [{"Operation": "0010"}]}}, [{"Operation": "0010"}]),
        ({"d": {"ManufacturingOrder": "1000000"}}, [{"ManufacturingOrder": "1000000"}]),
        ({"unexpected": []}, []),
    ],
)
def test_normalize_odata_supports_v2_and_v4(
    payload: dict[str, Any],
    expected: list[dict[str, Any]],
) -> None:
    assert mcp_server.normalize_odata(payload) == expected


def test_s4_repository_uses_sandbox_header_and_relative_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"d": {"results": [{"StatusCode": "I0002"}]}})

    repository = mcp_server.S4Repository(
        mcp_server.DEFAULT_S4_BASE_URL,
        "test-api-key",
        transport=httpx.MockTransport(handler),
    )
    result = repository.fetch("1000000", "to_ProductionOrderStatus")

    assert result == [{"StatusCode": "I0002"}]
    assert str(seen[0].url) == (
        f"{mcp_server.DEFAULT_S4_BASE_URL}/"
        "A_ProductionOrder_2('1000000')/to_ProductionOrderStatus?$format=json"
    )
    assert seen[0].headers["APIKey"] == "test-api-key"
    assert seen[0].headers["Accept"] == "application/json"


def test_s4_errors_do_not_expose_key_or_endpoint() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "private backend detail"})

    repository = mcp_server.S4Repository(
        "https://private.example.invalid/service",
        "secret-api-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError) as exc_info:
        repository.fetch("1000000", "to_ProductionOrderStatus")

    message = str(exc_info.value)
    assert "HTTP 503" in message
    assert "secret-api-key" not in message
    assert "private.example.invalid" not in message
    assert "private backend detail" not in message


def test_mock_mode_returns_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_MODE", "mock")
    first = mcp_server._fetch("1000000", "status", "to_ProductionOrderStatus")
    first[0]["StatusName"] = "changed"
    second = mcp_server._fetch("1000000", "status", "to_ProductionOrderStatus")
    assert second[0]["StatusName"] == "Released"


@pytest.mark.asyncio
async def test_mcp_tool_names_are_exact() -> None:
    result = await mcp_server.mcp.list_tools()
    assert {tool.name for tool in result} == {
        "get_production_order_operations",
        "get_production_order_status",
    }


@pytest.mark.parametrize(
    ("tool_name", "field"),
    [
        ("get_production_order_status", "status"),
        ("get_production_order_operations", "operations"),
    ],
)
@pytest.mark.asyncio
async def test_async_mcp_tools_preserve_mock_records(
    monkeypatch: pytest.MonkeyPatch, tool_name: str, field: str
) -> None:
    monkeypatch.setenv("DATA_MODE", "mock")
    result = await mcp_server.create_mcp_server().call_tool(
        tool_name, {"manufacturing_order": "1000000"}
    )
    assert result[1] == {"result": mcp_server.MOCK_ORDERS["1000000"][field]}


@pytest.mark.parametrize(
    ("tool_name", "navigation", "record"),
    [
        (
            "get_production_order_status",
            "to_ProductionOrderStatus",
            {"StatusName": "Released"},
        ),
        (
            "get_production_order_operations",
            "to_ProductionOrderOperation",
            {"ManufacturingOrderOperation": "0010"},
        ),
    ],
)
@pytest.mark.asyncio
async def test_slow_s4_tool_keeps_mcp_event_loop_responsive(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    navigation: str,
    record: dict[str, str],
) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_fetch(
        self: mcp_server.S4Repository, manufacturing_order: str, requested_navigation: str
    ) -> list[dict[str, Any]]:
        assert manufacturing_order == "1000000"
        assert requested_navigation == navigation
        started.set()
        release.wait(timeout=2)
        return [record]

    monkeypatch.setenv("DATA_MODE", "s4")
    monkeypatch.setenv("S4_BASE_URL", "https://synthetic.example.invalid/service")
    monkeypatch.setenv("S4_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(mcp_server.S4Repository, "fetch", slow_fetch)
    server = mcp_server.create_mcp_server()
    request = asyncio.create_task(server.call_tool(tool_name, {"manufacturing_order": "1000000"}))
    try:
        async with asyncio.timeout(5):
            while not started.is_set():
                await asyncio.sleep(0)
            assert not request.done(), "the event loop blocked until the sandbox fetch finished"
            tools = await server.list_tools()
            assert tool_name in {tool.name for tool in tools}
    finally:
        release.set()
        result = await request
    assert result[1] == {"result": [record]}
