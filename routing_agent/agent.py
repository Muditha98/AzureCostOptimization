import asyncio
import json
import logging
import os
import time
import uuid
import httpx

from typing import Any, Callable
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder, FunctionTool, MessageRole
from collections.abc import Callable
from dotenv import load_dotenv
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """A class to hold the connections to the remote agents."""

    def __init__(self, agent_card: AgentCard, agent_url: str):
        self._httpx_client = httpx.AsyncClient(timeout=30)
        self.agent_client = A2AClient(self._httpx_client, agent_card, url=agent_url)
        self.card = agent_card

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(self, message_request: SendMessageRequest) -> SendMessageResponse:
        return await self.agent_client.send_message(message_request)

class RoutingAgent:

    def __init__(self,task_callback: TaskUpdateCallback | None = None):

        self.task_callback = task_callback
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: str = ''
        
        # Initialize Azure AI Agents client
        self.agents_client = AgentsClient(
            endpoint=os.environ["PROJECT_ENDPOINT"],
            credential=DefaultAzureCredential(
                exclude_environment_credential=True,
                exclude_managed_identity_credential=True
            )
        )

        self.azure_agent = None
        self.current_thread = None


    @classmethod
    async def create(cls, remote_agent_addresses: list[str], task_callback: TaskUpdateCallback | None = None) -> 'RoutingAgent':
        """Create and asynchronously initialize an instance of the RoutingAgent."""
        instance = cls(task_callback)
        await instance._async_init_components(remote_agent_addresses)
        return instance
    

    def list_remote_agents(self) -> str:
        if not self.remote_agent_connections:
            return "[]"

        lines = []
        for card in self.cards.values():
            lines.append(f"{card.name}: {card.description}")

        return "[\n  " + ",\n  ".join(lines) + "\n]"
    

    async def _async_init_components(self, remote_agent_addresses: list[str]) -> None:
        """Asynchronous part of initialization."""

        # Use a single httpx.AsyncClient for all card resolutions for efficiency
        async with httpx.AsyncClient(timeout=30) as client:
            for address in remote_agent_addresses:
                card_resolver = A2ACardResolver(client, address)
                try:
                    card = await card_resolver.get_agent_card()

                    remote_connection = RemoteAgentConnections(agent_card=card, agent_url=address)
                    self.remote_agent_connections[card.name] = remote_connection
                    self.cards[card.name] = card

                except httpx.ConnectError as e:
                    logger.error(f'Failed to get agent card from {address}: {e}')
                except Exception as e:  # Catch other potential errors
                    logger.error(f'Failed to initialize connection for {address}: {e}')
            logger.info(f"Found remote agents: {self.list_remote_agents()}")

    
    async def send_message(self, agent_name: str, task: str):
        # Sends a task to remote agent.

        if agent_name not in self.remote_agent_connections:
            raise ValueError(f'Agent {agent_name} not found')

        # Retrieve the remote agent's A2A client using the agent name
        client = self.remote_agent_connections[agent_name]

        message_id = str(uuid.uuid4())

        # Construct the payload to send to the remote agent
        payload: dict[str, Any] = {
            'message': {
                'role': 'user',
                'parts': [{'kind': 'text', 'text': task}],
                'messageId': message_id,
            },
        }

        # Wrap the payload in a SendMessageRequest object
        message_request = SendMessageRequest(id=message_id, params=MessageSendParams.model_validate(payload))

        # Send the message to the remote agent client and await the response
        send_response: SendMessageResponse = await client.send_message(message_request=message_request)

        if not isinstance(send_response.root, SendMessageSuccessResponse):
            logger.warning('Received non-success response. Aborting get task')
            return

        if not isinstance(send_response.root.result, Task):
            logger.warning('Received non-task response. Aborting get task')
            return

        return send_response.root.result


    def create_agent(self):
        # Create an Azure AI Agent instance

        try:
            # Define the send_message function for Azure AI
            send_message_function = {
                "type": "function",
                "function": {
                    "name": "send_message",
                    "description": "Send a message to a specialized cloud cost optimization agent. Use this for analyzing Azure resources or creating optimization recommendations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_name": {
                                "type": "string",
                                "description": "The name of the agent to send the message to. Must be exactly 'Azure Cost Analysis Agent' for resource analysis or 'Azure Recommendation Agent' for optimization recommendations.",
                            },
                            "task": {
                                "type": "string",
                                "description": "The user's cost optimization request or question to be processed by the agent",
                            }
                        },
                        "required": ["agent_name", "task"]
                    }
                }
            }

            # Create Azure AI Agent with the send_message function
            self.azure_agent = self.agents_client.create_agent(
                model=os.environ["MODEL_DEPLOYMENT_NAME"],
                name="cost-optimization-routing-agent",
                instructions=f"""You are a cloud cost optimization routing agent. You MUST ALWAYS use the send_message function to delegate tasks to specialized cost optimization agents.

IMPORTANT: You cannot analyze costs or create recommendations yourself. You MUST call the send_message function.

Available Agents:
{self.list_remote_agents()}

ROUTING RULES:

1. **For Cost Analysis** (analyzing resources, identifying waste, finding opportunities):
   - User asks to: "analyze", "check", "find", "identify opportunities", "show waste"
   - Use agent_name: 'Azure Cost Analysis Agent'
   - Examples: "Analyze my VMs", "Find underutilized resources", "Check for cost savings"

2. **For Recommendations** (creating action plans, prioritizing, calculating ROI):
   - User asks to: "recommend", "create plan", "optimize", "prioritize", "generate recommendations"
   - Use agent_name: 'Azure Recommendation Agent'
   - Examples: "Create optimization plan", "Prioritize by ROI", "Generate recommendations"

3. **For Full Optimization Report** (analysis + recommendations):
   - First call 'Azure Cost Analysis Agent' to analyze
   - Then call 'Azure Recommendation Agent' with the analysis results
   - Combine both responses

ALWAYS pass the user's full request as the task parameter.

Example 1:
User: "Analyze my Azure VMs for cost savings"
You MUST call: send_message(agent_name='Azure Cost Analysis Agent', task='Analyze my Azure VMs for cost savings')

Example 2:
User: "Create an optimization plan"
You MUST call: send_message(agent_name='Azure Recommendation Agent', task='Create an optimization plan')

DO NOT respond directly. ALWAYS use send_message function.""",
                tools=[send_message_function]
            )

            # Create a thread for conversation
            self.current_thread = self.agents_client.threads.create()

            return self.azure_agent

        except Exception as e:
            logger.error(f"Error creating Azure AI agent: {e}", exc_info=True)
            raise

    async def process_user_message(self, user_message: str) -> str:

        if not hasattr(self, 'azure_agent') or not self.azure_agent:
            return "Azure AI Agent not initialized. Please ensure the agent is properly created."
        
        if not hasattr(self, 'current_thread') or not self.current_thread:
            return "Azure AI Thread not initialized. Please ensure the agent is properly created."
        
        try:
            # Create message in the thread
            self.agents_client.messages.create(
                thread_id=self.current_thread.id, 
                role=MessageRole.User, 
                content=user_message
            )

            # Create and run the agent
            run = self.agents_client.runs.create(
                thread_id=self.current_thread.id, 
                agent_id=self.azure_agent.id
            )
            
            # Need to await send_message function
            while run.status in ["queued", "in_progress", "requires_action"]:
                time.sleep(1)
                run = self.agents_client.runs.get(thread_id=self.current_thread.id, run_id=run.id)
                logger.info(f"Run status: {run.status}")

                if run.status == "requires_action":
                    logger.info(f"Function calling required: {run.required_action}")
                    tool_calls = run.required_action.submit_tool_outputs.tool_calls
                    tool_outputs = []
                    
                    for tool_call in tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)
                        
                        if function_name == "send_message":
                            try:
                                result = await self.send_message(agent_name=function_args["agent_name"], task=function_args["task"])
                                output = json.dumps(result.model_dump() if hasattr(result, 'model_dump') else str(result))

                            except Exception as e:
                                output = json.dumps({"error": str(e)})
                        else:
                            output = json.dumps({"error": f"Unknown function: {function_name}"})
                        
                        tool_outputs.append({"tool_call_id": tool_call.id,  "output": output})
                
                    # Submit the tool outputs
                    self.agents_client.runs.submit_tool_outputs(
                        thread_id=self.current_thread.id, run_id=run.id, tool_outputs=tool_outputs
                    )

            if run.status == "failed":
                error_info = f"Run error: {run.last_error}"
                logger.error(error_info)
                return f"Error processing request: {error_info}"

            # Return the response
            messages = self.agents_client.messages.list(thread_id=self.current_thread.id, order=ListSortOrder.DESCENDING)
            for msg in messages:
                # Check for both 'assistant' role and AGENT role for compatibility
                if (msg.role == 'assistant' or msg.role == MessageRole.AGENT) and msg.text_messages:
                    last_text = msg.text_messages[-1]
                    return last_text.text.value

            return "No response received from agent."

        except Exception as e:
            logger.error(f"Error in process_user_message: {e}", exc_info=True)
            return f"An error occurred while processing your message."


async def _get_initialized_routing_agent_sync() -> RoutingAgent:

    async def _async_main() -> RoutingAgent:
        routing_agent_instance = await RoutingAgent.create(
            remote_agent_addresses=[
                f"http://{os.environ["SERVER_URL"]}:{os.environ["TITLE_AGENT_PORT"]}",
                f"http://{os.environ["SERVER_URL"]}:{os.environ["OUTLINE_AGENT_PORT"]}",
            ]
        )
        # Create the Azure AI agent
        routing_agent_instance.create_agent()
        return routing_agent_instance

    try:
        return asyncio.run(_async_main())
    except RuntimeError as e:
        raise

# Initialize the routing agent
routing_agent = _get_initialized_routing_agent_sync()
