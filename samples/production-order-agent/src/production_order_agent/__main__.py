"""A2A v1.0 server for the production-order sample."""

from __future__ import annotations

import logging

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

from production_order_agent.agent import ProductionOrderAgent
from production_order_agent.settings import Settings

LOGGER = logging.getLogger("production_order_agent")


def build_agent_card(base_url: str) -> AgentCard:
    return AgentCard(
        name="Production Order Agent",
        description=(
            "Retrieves SAP S/4HANA production-order status and scheduled operations "
            "through MCP and highlights potential delays."
        ),
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
                id="production_order_lookup",
                name="Production Order Lookup",
                description=(
                    "Return status and scheduled operations for a numeric manufacturing "
                    "order and identify overdue, unconfirmed operations."
                ),
                tags=["manufacturing", "production order", "SAP S/4HANA", "MCP"],
                examples=[
                    "Why is production order 1000000 delayed?",
                    "Show the status and operations for order 1000000.",
                ],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
            )
        ],
    )


class ProductionOrderAgentExecutor(AgentExecutor):
    def __init__(self, agent: ProductionOrderAgent | None = None) -> None:
        self.agent = agent or ProductionOrderAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        try:
            answer = await self.agent.invoke(context.get_user_input())
        except Exception as exc:
            LOGGER.warning("production-order request failed: %s", type(exc).__name__)
            await updater.add_artifact(
                parts=[
                    new_text_part(
                        "The production-order data could not be retrieved. "
                        "Check the MCP server and its data-source configuration.",
                        "text/plain",
                    )
                ],
                name="error",
            )
            await updater.failed()
            return

        await updater.add_artifact(
            parts=[new_text_part(answer, "text/plain")],
            name="production-order-summary",
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancellation is not supported.")


def create_app(
    base_url: str = "http://127.0.0.1:8000",
    *,
    agent: ProductionOrderAgent | None = None,
) -> Starlette:
    agent_card = build_agent_card(base_url)
    request_handler = DefaultRequestHandler(
        agent_executor=ProductionOrderAgentExecutor(agent),
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
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    uvicorn.run(
        app=create_app(settings.url),
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
