"""Small, allowlisted MCP client used by the A2A agent."""

from __future__ import annotations

import json
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

ALLOWED_TOOLS = {
    "get_production_order_operations",
    "get_production_order_status",
}


def tool_result_data(result: Any) -> list[dict[str, Any]]:
    """Normalize structured or text MCP results into a list of records."""

    is_error = getattr(result, "is_error", getattr(result, "isError", False))
    if is_error:
        raise RuntimeError("MCP tool returned an error")

    structured = getattr(
        result,
        "structured_content",
        getattr(result, "structuredContent", None),
    )
    if structured is not None:
        data = structured.get("result", structured) if isinstance(structured, dict) else structured
        if isinstance(data, list):
            return [item if isinstance(item, dict) else {"value": item} for item in data]
        if isinstance(data, dict):
            return [data]

    text = "\n".join(
        part.text
        for part in getattr(result, "content", [])
        if getattr(part, "type", "") == "text" and getattr(part, "text", "")
    ).strip()
    if not text:
        raise RuntimeError("MCP tool returned no usable data")

    parsed = json.loads(text)
    if isinstance(parsed, dict) and "result" in parsed:
        parsed = parsed["result"]
    if isinstance(parsed, list):
        return [item if isinstance(item, dict) else {"value": item} for item in parsed]
    if isinstance(parsed, dict):
        return [parsed]
    raise RuntimeError("MCP tool returned an unsupported data shape")


async def call_mcp_tool(
    server_url: str,
    tool_name: str,
    manufacturing_order: str,
) -> list[dict[str, Any]]:
    """Call one production-order tool over MCP SSE."""

    if tool_name not in ALLOWED_TOOLS:
        raise ValueError(f"unsupported MCP tool: {tool_name}")
    if not server_url.strip():
        raise ValueError("MCP_SERVER_URL is required")

    async with (
        sse_client(server_url) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool(
            tool_name,
            arguments={"manufacturing_order": manufacturing_order},
        )

    return tool_result_data(result)
