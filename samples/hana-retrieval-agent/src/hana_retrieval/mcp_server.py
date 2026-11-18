"""Bounded retrieval tools over a selected backend."""

import asyncio
import logging
import os

from mcp.server.fastmcp import FastMCP

from hana_retrieval.embedding import dimension, embed
from hana_retrieval.fixture import FixtureRepository
from hana_retrieval.repository import SUBJECT, HanaRepository, limit_value

mcp = FastMCP(
    "hana-retrieval",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8092")),
)

logging.getLogger("httpx2").setLevel(logging.WARNING)
logging.getLogger("httpcore2").setLevel(logging.WARNING)


def repository():
    backend = os.environ.get("RETRIEVAL_BACKEND", "fixture")
    if backend == "fixture":
        return FixtureRepository()
    if backend == "hana":
        return HanaRepository(
            os.environ["HANA_SCHEMA"], os.environ["HANA_GRAPH"], dimension=dimension()
        )
    raise ValueError("RETRIEVAL_BACKEND must be fixture or hana")


@mcp.tool()
async def retrieve_context(query: str, topic: str, limit: int = 5) -> list[dict]:
    """Read at most 20 source-linked documents within one metadata topic."""
    limit_value(limit)
    if not query or len(query) > 2000 or not topic or len(topic) > 128:
        raise ValueError("query and topic exceed the retrieval contract")
    repo = repository()
    vector = (
        [1.0, 0.0, 0.0]
        if isinstance(repo, FixtureRepository)
        else await asyncio.to_thread(embed, query, dimension())
    )
    return await asyncio.to_thread(repo.vector, vector, topic, limit)


@mcp.tool()
async def lookup_relationships(subject: str, limit: int = 5) -> list[dict]:
    """Read primary-contact relationships for one entity from the configured graph."""
    limit_value(limit)
    if not SUBJECT.fullmatch(subject):
        raise ValueError("subject must be a bounded entity identifier")
    return await asyncio.to_thread(repository().graph, subject, limit)


if __name__ == "__main__":
    mcp.run(transport="sse")
