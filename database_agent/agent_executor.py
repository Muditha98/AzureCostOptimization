""" Azure AI Foundry Agent Executor for Azure Database Optimization """

import logging
from a2a.server.events.event_queue import EventQueue
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.utils import new_agent_text_message
from a2a.types import AgentCard, Part, TaskState
from database_agent.agent import DatabaseAgent, create_foundry_database_agent

logger = logging.getLogger(__name__)

class FoundryAgentExecutor(AgentExecutor):

    def __init__(self, card: AgentCard):
        self._card = card
        self._foundry_agent: DatabaseAgent | None = None

    async def _get_or_create_agent(self) -> DatabaseAgent:
        if not self._foundry_agent:
            self._foundry_agent = await create_foundry_database_agent()
        return self._foundry_agent

    async def _process_request(self, message_parts: list[Part], context_id: str, task_updater: TaskUpdater) -> None:
        # Process a user request through the Database Agent

        try:
            # Retrieve message from A2A parts
            user_message = message_parts[0].root.text

            # Get the database agent
            agent = await self._get_or_create_agent()

            # Update the task status
            await task_updater.update_status(
                TaskState.working,
                message=new_agent_text_message('Database Agent is analyzing your SQL and Cosmos DB resources...', context_id=context_id)
            )

            # Run the agent conversation (includes function calling)
            responses = await agent.run_conversation(user_message)

            # Update the task with responses
            for response in responses:
                await task_updater.update_status(
                    TaskState.working,
                    message=new_agent_text_message(response, context_id=context_id)
                )

            # Mark the task as complete
            final_message = responses[-1] if responses else 'Database analysis completed.'
            await task_updater.complete(
                message=new_agent_text_message(final_message, context_id=context_id)
            )

        except Exception as e:
            logger.error(f'Database Agent: Error processing request - {e}', exc_info=True)
            await task_updater.failed(
                message=new_agent_text_message("Database Agent failed to process the request.",
                context_id=context_id)
            )

    async def execute(self, context: RequestContext, event_queue: EventQueue,):

        # Create task updater
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.submit()

        # Start working
        await updater.start_work()

        # Process the request
        await self._process_request(context.message.parts, context.context_id, updater)

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        logger.info(f'Database Agent: Cancelling execution for context {context.context_id}')

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.failed(
            message=new_agent_text_message('Task cancelled by user', context_id=context.context_id)
        )

def create_foundry_agent_executor(card: AgentCard) -> FoundryAgentExecutor:
    return FoundryAgentExecutor(card)
