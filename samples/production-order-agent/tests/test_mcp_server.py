from __future__ import annotations

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
