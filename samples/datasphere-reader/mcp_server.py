"""One bounded tool over a configured Datasphere view."""

import logging
import os

from mcp.server.fastmcp import FastMCP

from datasphere import DatasphereReader

mcp = FastMCP(
    "datasphere-reader",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8091")),
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@mcp.tool()
async def read_region_revenue(region: str, limit: int = 50) -> dict:
    """Read at most 50 revenue rows for one region from the configured view."""
    if not region or len(region) > 128 or not 1 <= limit <= 50:
        raise ValueError("region must contain 1-128 characters and limit must be 1-50")
    async with DatasphereReader(
        base_url=os.environ["BDC_ODATA_BASE_URL"],
        space=os.environ["BDC_SPACE"],
        view=os.environ["BDC_VIEW"],
        shape=os.environ["BDC_SHAPE"],
        token_url=os.environ["BDC_TOKEN_URL"],
        client_id=os.environ["BDC_CLIENT_ID"],
        client_secret=os.environ["BDC_CLIENT_SECRET"],
    ) as reader:
        rows = await reader.read(
            select=["Region", "Revenue"], equal={"Region": region}, limit=limit
        )
    return {"rows": rows, "source": "configured Datasphere revenue view", "limit": limit}


if __name__ == "__main__":
    mcp.run(transport="sse")
