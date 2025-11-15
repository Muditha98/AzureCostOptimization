"""
Recommendation Agent

This agent aggregates findings from all specialized agents and provides
comprehensive Azure cost optimization recommendations.
"""

import os
import json
import logging
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import Agent, ListSortOrder, MessageRole
from recommendation_agent.agent_helpers import (
    aggregate_compute_findings,
    aggregate_storage_findings,
    aggregate_database_findings,
    aggregate_network_findings,
    aggregate_cost_findings,
    generate_summary_report,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Function tool definitions for aggregating findings
RECOMMENDATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "aggregate_compute_findings",
            "description": "Get compute optimization findings from the Compute Agent. Returns query details to fetch VM right-sizing and optimization recommendations.",
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
            "name": "aggregate_storage_findings",
            "description": "Get storage optimization findings from the Storage Agent. Returns query details to fetch disk, blob, and storage account optimizations.",
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
            "name": "aggregate_database_findings",
            "description": "Get database optimization findings from the Database Agent. Returns query details to fetch SQL and Cosmos DB optimization recommendations.",
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
            "name": "aggregate_network_findings",
            "description": "Get network optimization findings from the Network Agent. Returns query details to fetch public IP, load balancer, and NIC optimizations.",
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
            "name": "aggregate_cost_findings",
            "description": "Get cost analysis findings from the Cost Analysis Agent. Returns query details to fetch spending trends and cost breakdown analysis.",
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
            "name": "generate_summary_report",
            "description": "Generate a comprehensive summary report aggregating all findings. Takes responses from all specialized agents as input.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_responses": {
                        "type": "string",
                        "description": "JSON string containing responses from all specialized agents"
                    }
                },
                "required": ["agent_responses"]
            }
        }
    },
]


class RecommendationAgent:
    """Agent that aggregates findings from specialized agents and provides holistic recommendations."""

    def __init__(self):
        """Initialize the Recommendation Agent with Azure AI Agents client."""
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

        # Create the recommendation agent with function tools
        self.agent = self.client.create_agent(
            model=os.environ['MODEL_DEPLOYMENT_NAME'],
            name='foundry-recommendation-agent',
            instructions="""You are an Azure cost optimization strategist and orchestrator.

Your role is to:
1. Coordinate with specialized agents (compute, storage, database, network, cost analysis)
2. Aggregate their findings into a cohesive optimization strategy
3. Prioritize recommendations by impact (savings) and effort
4. Provide a comprehensive, actionable optimization roadmap

When the user asks for comprehensive recommendations:
1. Use the aggregate functions to get query details for each specialized agent
2. Explain that you're gathering data from multiple specialized agents
3. Use the generate_summary_report function to create a holistic report
4. Present findings in order of priority:
   - Quick wins (high savings, low effort): unattached resources, right-sizing VMs
   - Medium term: elastic pool consolidation, storage tier optimization
   - Strategic: multi-region optimization, reserved instances

Your recommendations should:
- Be specific and actionable (exact resources, commands, expected savings)
- Prioritize by ROI (return on investment)
- Group related optimizations together
- Include both immediate actions and long-term strategies
- Provide estimated monthly/annual savings for each recommendation category

Always start comprehensive analyses by gathering data from all relevant specialized agents.
Present a cohesive strategy rather than disconnected recommendations.""",
            tools=RECOMMENDATION_TOOLS,
        )
        logger.info(f"Recommendation Agent created with ID: {self.agent.id}")
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
                logger.info(f"Recommendation Agent: Executing {len(tool_calls)} function call(s)")

                tool_outputs = []
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    logger.info(f"Calling function: {function_name}")

                    # Execute the appropriate function
                    try:
                        if function_name == 'aggregate_compute_findings':
                            result = aggregate_compute_findings()
                        elif function_name == 'aggregate_storage_findings':
                            result = aggregate_storage_findings()
                        elif function_name == 'aggregate_database_findings':
                            result = aggregate_database_findings()
                        elif function_name == 'aggregate_network_findings':
                            result = aggregate_network_findings()
                        elif function_name == 'aggregate_cost_findings':
                            result = aggregate_cost_findings()
                        elif function_name == 'generate_summary_report':
                            # Parse arguments
                            args = json.loads(tool_call.function.arguments)
                            agent_responses = json.loads(args.get("agent_responses", "{}"))
                            result = generate_summary_report(agent_responses)
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
            logger.error(f'Recommendation Agent: Run failed - {run.last_error}')
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


async def create_foundry_recommendation_agent() -> RecommendationAgent:
    """Create and return a recommendation agent instance."""
    agent = RecommendationAgent()
    await agent.create_agent()
    return agent
