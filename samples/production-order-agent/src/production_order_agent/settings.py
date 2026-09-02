"""Environment-backed settings with credential-free defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    url: str = "http://127.0.0.1:8000"
    mcp_server_url: str = "http://127.0.0.1:8090/sse"
    llm_provider: str = "mock"
    model_name: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "8000"))
        return cls(
            host=host,
            port=port,
            url=os.getenv("URL", f"http://{host}:{port}"),
            mcp_server_url=os.getenv(
                "MCP_SERVER_URL",
                "http://127.0.0.1:8090/sse",
            ),
            llm_provider=os.getenv("LLM_PROVIDER", "mock").strip().lower(),
            model_name=os.getenv("MODEL_NAME", "").strip(),
        )
