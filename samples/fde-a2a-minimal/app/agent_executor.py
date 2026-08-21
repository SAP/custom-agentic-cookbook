from a2a.helpers import new_task_from_user_message, new_text_message
from a2a.helpers.proto_helpers import new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

from app.agent import HelloWorldAgent


class HelloWorldAgentExecutor(AgentExecutor):
    def __init__(self) -> None:
        self.agent = HelloWorldAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work(
            new_text_message(
                "Processing request...",
                "text/plain",
                task.context_id,
                task.id,
            )
        )

        result = await self.agent.invoke()

        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            new_text_message(
                "Returning result...",
                "text/plain",
                task.context_id,
                task.id,
            ),
        )
        await updater.add_artifact(
            parts=[new_text_part(result, "text/plain")],
            name="result",
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancellation is not supported.")
