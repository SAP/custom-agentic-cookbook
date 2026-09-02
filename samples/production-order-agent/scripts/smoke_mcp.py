"""Verify that the sample MCP server exposes the expected tools."""

from __future__ import annotations

import argparse
import asyncio
import json

from mcp import ClientSession
from mcp.client.sse import sse_client

EXPECTED_TOOLS = {
    "get_production_order_operations",
    "get_production_order_status",
}


async def run(server_url: str) -> dict[str, list[str]]:
    async with (
        sse_client(server_url) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.list_tools()

    tool_names = {tool.name for tool in result.tools}
    if tool_names != EXPECTED_TOOLS:
        raise RuntimeError(f"expected MCP tools {sorted(EXPECTED_TOOLS)}, got {sorted(tool_names)}")
    return {"tools": sorted(tool_names)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", default="http://127.0.0.1:8090/sse")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.server_url)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
