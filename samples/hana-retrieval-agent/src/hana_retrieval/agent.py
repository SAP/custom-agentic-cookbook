"""A2A answers include retrieved facts and source references."""

import os

from mcp import ClientSession
from mcp.client.sse import sse_client


class RetrievalAgent:
    async def invoke(self, text):
        if text.startswith("vector:"):
            parts = text.split(":", 2)
            if len(parts) != 3:
                return "Use vector:topic:question or graph:entity-id."
            name, arguments = "retrieve_context", {"topic": parts[1], "query": parts[2], "limit": 5}
        elif text.startswith("graph:"):
            name, arguments = "lookup_relationships", {"subject": text[6:].strip(), "limit": 5}
        else:
            return "Use vector:topic:question or graph:entity-id."
        url = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8092/sse")
        async with sse_client(url) as streams, ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
        if result.isError:
            raise RuntimeError("retrieval tool failed")
        data = result.structuredContent
        rows = data.get("result", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise RuntimeError("retrieval tool returned malformed records")
        if not rows:
            return "No matching source records were returned."
        return "Retrieved context\n" + "\n".join(
            f"{row.get('content', row.get('contact', ''))} [source: {row['source']}]"
            for row in rows
        )
