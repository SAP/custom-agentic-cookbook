"""MCP tools for SAP S/4HANA production-order status and operations."""

from __future__ import annotations

import copy
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_S4_BASE_URL = (
    "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV"
)

MOCK_ORDERS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "1000000": {
        "status": [
            {
                "ManufacturingOrder": "1000000",
                "StatusCode": "I0002",
                "StatusName": "Released",
            },
            {
                "ManufacturingOrder": "1000000",
                "StatusCode": "I0045",
                "StatusName": "Partially Confirmed",
            },
        ],
        "operations": [
            {
                "ManufacturingOrder": "1000000",
                "ManufacturingOrderOperation": "0010",
                "MfgOrderOperationText": "Prepare components",
                "WorkCenter": "ASSEMBLY-01",
                "OpErlstSchedldExecStrtDte": "2024-01-15",
                "OpErlstSchedldExecEndDte": "2024-01-15",
                "OperationIsFinallyConfirmed": True,
            },
            {
                "ManufacturingOrder": "1000000",
                "ManufacturingOrderOperation": "0020",
                "MfgOrderOperationText": "Final assembly",
                "WorkCenter": "ASSEMBLY-02",
                "OpErlstSchedldExecStrtDte": "2024-01-16",
                "OpErlstSchedldExecEndDte": "2024-01-16",
                "OperationIsFinallyConfirmed": False,
            },
        ],
    }
}


def validate_order_id(manufacturing_order: str) -> str:
    order = manufacturing_order.strip()
    if not order.isascii() or not order.isdigit() or len(order) > 20:
        raise ValueError("manufacturing_order must be 1-20 ASCII digits")
    return order


def order_path(manufacturing_order: str, navigation: str) -> str:
    order = validate_order_id(manufacturing_order)
    allowed = {"to_ProductionOrderOperation", "to_ProductionOrderStatus"}
    if navigation not in allowed:
        raise ValueError("unsupported production-order navigation")
    return f"A_ProductionOrder_2('{order}')/{navigation}?$format=json"


def normalize_odata(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept the OData v2 sandbox and OData v4 response envelopes."""

    data: Any
    if "value" in payload:
        data = payload["value"]
    elif isinstance(payload.get("d"), dict):
        data = payload["d"].get("results", payload["d"])
    else:
        return []

    if not isinstance(data, list):
        data = [data]
    return [item for item in data if isinstance(item, dict)]


class S4Repository:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.strip():
            raise RuntimeError("S4_BASE_URL is required when DATA_MODE=s4")
        if not api_key.strip():
            raise RuntimeError("S4_API_KEY is required when DATA_MODE=s4")
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.transport = transport

    def fetch(self, manufacturing_order: str, navigation: str) -> list[dict[str, Any]]:
        with httpx.Client(
            base_url=self.base_url,
            headers={"APIKey": self.api_key, "Accept": "application/json"},
            timeout=20,
            transport=self.transport,
        ) as client:
            response = client.get(order_path(manufacturing_order, navigation))

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"S/4 request failed with HTTP {response.status_code}") from exc
        return normalize_odata(response.json())


def _mock_fetch(manufacturing_order: str, field: str) -> list[dict[str, Any]]:
    order = validate_order_id(manufacturing_order)
    record = MOCK_ORDERS.get(order)
    if record is None:
        raise LookupError(f"mock production order {order} was not found")
    return copy.deepcopy(record[field])


def _fetch(manufacturing_order: str, field: str, navigation: str) -> list[dict[str, Any]]:
    mode = os.getenv("DATA_MODE", "mock").strip().lower()
    if mode == "mock":
        return _mock_fetch(manufacturing_order, field)
    if mode == "s4":
        repository = S4Repository(
            os.getenv("S4_BASE_URL", DEFAULT_S4_BASE_URL),
            os.getenv("S4_API_KEY", ""),
        )
        return repository.fetch(manufacturing_order, navigation)
    raise RuntimeError("DATA_MODE must be 'mock' or 's4'")


def create_mcp_server() -> FastMCP:
    server = FastMCP(
        "production-order-mcp",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8090")),
    )

    @server.tool()
    def get_production_order_status(manufacturing_order: str) -> list[dict[str, Any]]:
        """Return active status records for an SAP S/4HANA production order."""

        return _fetch(
            manufacturing_order,
            "status",
            "to_ProductionOrderStatus",
        )

    @server.tool()
    def get_production_order_operations(manufacturing_order: str) -> list[dict[str, Any]]:
        """Return scheduled operations for an SAP S/4HANA production order."""

        return _fetch(
            manufacturing_order,
            "operations",
            "to_ProductionOrderOperation",
        )

    return server


mcp = create_mcp_server()


def main() -> None:
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
