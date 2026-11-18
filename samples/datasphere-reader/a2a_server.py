"""Optional loopback A2A v1.0 revenue consumer of the Datasphere MCP tool."""

import logging
import os
from urllib.parse import urlsplit

import uvicorn
from a2a.helpers import new_task_from_user_message
from a2a.helpers.proto_helpers import new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette

from revenue_agent import RevenueAgent


class RevenueExecutor(AgentExecutor):
    def __init__(self, agent):
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        try:
            answer = await self.agent.invoke(context.get_user_input())
        except Exception:
            await updater.add_artifact(
                parts=[
                    new_text_part(
                        "Revenue data could not be retrieved. "
                        "Check the MCP service and approved configuration.",
                        "text/plain",
                    )
                ],
                name="error",
            )
            await updater.failed()
            return
        await updater.add_artifact(
            parts=[new_text_part(answer, "text/plain")], name="revenue-summary"
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancellation is not supported.")


def create_app(base_url: str = "http://127.0.0.1:8001", *, agent=None) -> Starlette:
    try:
        parsed = urlsplit(base_url)
        if (
            len(base_url) > 2048
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError
        _ = parsed.port
    except ValueError:
        raise ValueError(
            "URL must be an HTTP origin without credentials, query or fragment"
        ) from None
    card = AgentCard(
        name="Revenue Reader",
        description="Return a bounded revenue total through one configured MCP tool.",
        supported_interfaces=[
            AgentInterface(url=base_url, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="revenue_lookup",
                name="Bounded region revenue",
                description=(
                    "Use revenue <region>; read at most 50 rows. "
                    "This is a bounded result, not a complete aggregate."
                ),
                tags=["revenue", "MCP"],
                examples=["revenue EMEA"],
            )
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=RevenueExecutor(agent or RevenueAgent()),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    return Starlette(
        routes=[
            *create_agent_card_routes(card),
            *create_jsonrpc_routes(request_handler=handler, rpc_url="/", enable_v0_3_compat=False),
        ]
    )


def main() -> None:
    mode = os.getenv("A2A_SOURCE_MODE", "datasphere")
    if mode not in {"datasphere", "fixture"}:
        raise ValueError("A2A_SOURCE_MODE must be datasphere or fixture")
    port = int(os.getenv("PORT", "8001"))
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    uvicorn.run(
        create_app(
            os.getenv("URL", f"http://127.0.0.1:{port}"),
            agent=RevenueAgent(fixture=mode == "fixture"),
        ),
        host="127.0.0.1",
        port=port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
