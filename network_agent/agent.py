"""
Network Optimization Agent

This agent specializes in analyzing Azure network resources
for cost optimization opportunities.
"""

import os
import json
import logging
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import Agent, ListSortOrder, MessageRole
from network_agent.azure_helpers import (
    list_unattached_public_ips,
    analyze_load_balancers,
    analyze_network_interfaces,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Function tool definitions for Azure network operations
NETWORK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_unattached_public_ips",
            "description": "Find public IP addresses that are not attached to any resource. Unattached IPs still incur monthly charges and represent waste.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_load_balancers",
            "description": "Analyze Azure load balancers for optimization opportunities. Identifies unused load balancers and provides SKU recommendations.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_network_interfaces",
            "description": "Analyze network interfaces (NICs) for optimization. Identifies unused NICs and provides accelerated networking recommendations.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


class NetworkAgent:
    """Agent that provides Azure network cost optimization recommendations."""

    def __init__(self):
        """Initialize the Network Agent with Azure AI Agents client."""
        # Create the agents client
        self.client = AgentsClient(
            endpoint=os.environ['PROJECT_ENDPOINT'],
            credential=DefaultAzureCredential(
                exclude_environment_credential=True,
                exclude_managed_identity_credential=True
            )
        )
        self.agent: Agent | None = None

    async def create_agent(self) -> Agent:
        if self.agent:
            return self.agent

        # Create the network optimization agent with function tools
        self.agent = self.client.create_agent(
            model=os.environ['MODEL_DEPLOYMENT_NAME'],
            name='foundry-network-agent',
            instructions="""You are an Azure network cost optimization specialist.

You help users optimize their Azure network resources by:
1. Identifying unattached public IP addresses that are wasting money
2. Analyzing load balancers for unused or underutilized instances
3. Finding unused network interfaces that can be cleaned up
4. Recommending accelerated networking for better performance
5. Providing specific Azure CLI commands for cleanup and optimization

When analyzing network resources:
- Focus on identifying waste (unattached IPs, unused NICs, idle load balancers)
- Calculate monthly and annual cost savings for each optimization
- Provide specific Azure CLI commands for implementing recommendations
- Consider both cost optimization and performance improvements
- Explain the impact of Standard vs Basic SKU for load balancers

Always provide actionable recommendations with specific resource names, Azure CLI commands, and estimated cost savings.
Always use the functions to get real data before providing recommendations.""",
            tools=NETWORK_TOOLS,
        )
        logger.info(f"Network Agent created with ID: {self.agent.id}")
        return self.agent

    async def run_conversation(self, user_message: str) -> list[str]:
        if not self.agent:
            await self.create_agent()

        # Create a thread for the chat session
        thread = self.client.threads.create()

        # Send user message
        self.client.messages.create(thread_id=thread.id, role=MessageRole.USER, content=user_message)

        # Create a run
        run = self.client.runs.create(thread_id=thread.id, agent_id=self.agent.id)

        # Function calling loop - poll until completion
        while run.status in ['queued', 'in_progress', 'requires_action']:
            # Wait a bit before polling
            import time
            time.sleep(0.5)

            # Get the latest run status
            run = self.client.runs.get(thread_id=thread.id, run_id=run.id)

            # Handle function calls
            if run.status == 'requires_action':
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                logger.info(f"Network Agent: Executing {len(tool_calls)} function call(s)")

                tool_outputs = []
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    logger.info(f"Calling function: {function_name}")

                    # Execute the appropriate function
                    try:
                        if function_name == 'list_unattached_public_ips':
                            result = list_unattached_public_ips()
                        elif function_name == 'analyze_load_balancers':
                            result = analyze_load_balancers()
                        elif function_name == 'analyze_network_interfaces':
                            result = analyze_network_interfaces()
                        else:
                            result = json.dumps({"error": f"Unknown function: {function_name}"})

                        logger.info(f"Function {function_name} completed successfully")

                        tool_outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": result
                        })
                    except Exception as e:
                        logger.error(f"Error executing {function_name}: {e}", exc_info=True)
                        tool_outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": json.dumps({"error": str(e)})
                        })

                # Submit tool outputs back to the agent
                run = self.client.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )

        # Check for failures
        if run.status == 'failed':
            logger.error(f'Network Agent: Run failed - {run.last_error}')
            return [f'Error: {run.last_error}']

        # Get response messages
        messages = self.client.messages.list(thread_id=thread.id, order=ListSortOrder.DESCENDING)
        responses = []
        for msg in messages:
            if msg.role == MessageRole.ASSISTANT:
                for item in msg.content:
                    if hasattr(item, 'text') and hasattr(item.text, 'value'):
                        responses.append(item.text.value)

        return responses


async def create_foundry_network_agent() -> NetworkAgent:
    """Create and return a network agent instance."""
    agent = NetworkAgent()
    await agent.create_agent()
    return agent
