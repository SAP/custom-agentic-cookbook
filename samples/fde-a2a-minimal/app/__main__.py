import os

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette

from app.agent_executor import HelloWorldAgentExecutor


def build_agent_card(base_url: str) -> AgentCard:
    return AgentCard(
        name="Hello World Agent",
        description="An agent that responds with 'Hello, World!' to any message.",
        supported_interfaces=[
            AgentInterface(
                url=base_url,
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            )
        ],
        version="0.1.0",
        capabilities=AgentCapabilities(
            streaming=False,
            push_notifications=False,
            extended_agent_card=False,
        ),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="hello_world_skill",
                name="Hello World Skill",
                description="Return 'Hello, World!' for any message.",
                tags=["hello world"],
                examples=["hi", "hello", "hey"],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
            )
        ],
    )


def create_app(base_url: str = "http://127.0.0.1:8000") -> Starlette:
    agent_card = build_agent_card(base_url)
    request_handler = DefaultRequestHandler(
        agent_executor=HelloWorldAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    return Starlette(
        routes=[
            *create_agent_card_routes(agent_card),
            *create_jsonrpc_routes(
                request_handler=request_handler,
                rpc_url="/",
                enable_v0_3_compat=False,
            ),
        ]
    )


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    base_url = os.getenv("URL", f"http://{host}:{port}")
    uvicorn.run(app=create_app(base_url), host=host, port=port)


if __name__ == "__main__":
    main()
