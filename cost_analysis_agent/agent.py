"""
Cost Analysis Agent

This agent specializes in analyzing Azure spending patterns and cost trends
using the Azure Cost Management API.
"""

import os
import json
import logging
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import Agent, ListSortOrder, MessageRole
from cost_analysis_agent.azure_helpers import (
    get_current_month_costs,
    get_cost_by_resource_group,
    get_cost_trends,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Function tool definitions for Azure cost analysis
COST_ANALYSIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_month_costs",
            "description": "Get current month's Azure costs with breakdown by service. Shows which Azure services are contributing most to the bill.",
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
            "name": "get_cost_by_resource_group",
            "description": "Analyze costs broken down by resource group. Identifies which resource groups are most expensive.",
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
            "name": "get_cost_trends",
            "description": "Analyze cost trends over the past 3 months. Shows spending patterns and identifies cost increases or decreases.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


class CostAnalysisAgent:
    """Agent that provides Azure cost analysis and spending insights."""

    def __init__(self):
        """Initialize the Cost Analysis Agent with Azure AI Agents client."""
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

        # Create the cost analysis agent with function tools
        self.agent = self.client.create_agent(
            model=os.environ['MODEL_DEPLOYMENT_NAME'],
            name='foundry-cost-analysis-agent',
            instructions="""You are an Azure cost analysis specialist.

You help users understand their Azure spending by:
1. Analyzing current month costs and service-level breakdown
2. Identifying which resource groups are most expensive
3. Tracking cost trends over time (3-month analysis)
4. Identifying cost spikes and anomalies
5. Providing insights into spending patterns

When analyzing costs:
- Focus on the biggest cost drivers (services, resource groups)
- Identify unusual spending patterns or recent increases
- Provide context about which services typically cost more
- Calculate month-over-month trends and percentage changes
- Highlight opportunities for cost reduction based on spending patterns

Always present cost data in a clear, actionable format with specific recommendations for the largest cost items.
Always use the functions to get real data before providing recommendations.""",
            tools=COST_ANALYSIS_TOOLS,
        )
        logger.info(f"Cost Analysis Agent created with ID: {self.agent.id}")
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
                logger.info(f"Cost Analysis Agent: Executing {len(tool_calls)} function call(s)")

                tool_outputs = []
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    logger.info(f"Calling function: {function_name}")

                    # Execute the appropriate function
                    try:
                        if function_name == 'get_current_month_costs':
                            result = get_current_month_costs()
                        elif function_name == 'get_cost_by_resource_group':
                            result = get_cost_by_resource_group()
                        elif function_name == 'get_cost_trends':
                            result = get_cost_trends()
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
            logger.error(f'Cost Analysis Agent: Run failed - {run.last_error}')
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


async def create_foundry_cost_analysis_agent() -> CostAnalysisAgent:
    """Create and return a cost analysis agent instance."""
    agent = CostAnalysisAgent()
    await agent.create_agent()
    return agent
