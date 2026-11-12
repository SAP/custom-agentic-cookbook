"""Validation-only reader factory: permit exactly the packaged loopback fixture."""

import os

import mcp_server
from datasphere import DatasphereReader


def fixture_reader(**kwargs):
    shape = os.environ["BDC_SHAPE"]
    expected = "http://127.0.0.1:8093" + ("/SPACE" if shape == "A" else "/relational")
    if (
        kwargs["base_url"] != expected
        or kwargs["token_url"] != f"http://127.0.0.1:8093/token/{shape}"
    ):
        raise ValueError("validation wrapper accepts only its exact loopback fixture")
    return DatasphereReader(**kwargs, allow_http=True)


if __name__ == "__main__":
    if os.environ.get("A2A_SOURCE_MODE") != "fixture" or os.environ.get("MCP_HOST") != "127.0.0.1":
        raise ValueError("validation wrapper requires private fixture mode and loopback")
    mcp_server.DatasphereReader = fixture_reader
    mcp_server.mcp.run(transport="sse")
