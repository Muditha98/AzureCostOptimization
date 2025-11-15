"""
Database Optimization Agent

This agent specializes in analyzing Azure SQL and Cosmos DB resources
for cost optimization opportunities.
"""

import os
import json
import logging
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import Agent, ListSortOrder, MessageRole
from database_agent.azure_helpers import (
    list_sql_databases,
    analyze_sql_elastic_pools,
    list_cosmos_db_accounts,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Function tool definitions for Azure database operations
DATABASE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_sql_databases",
            "description": "List all Azure SQL databases with utilization metrics and cost information. Provides recommendations for database optimization including tier adjustments and cost savings.",
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
            "name": "analyze_sql_elastic_pools",
            "description": "Analyze SQL elastic pools and identify opportunities for cost optimization. Recommends consolidating standalone databases into elastic pools when beneficial.",
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
            "name": "list_cosmos_db_accounts",
            "description": "List all Cosmos DB accounts with configuration and throughput analysis. Provides recommendations for multi-region setups, consistency policies, and throughput optimization.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


class DatabaseAgent:
    """Agent that provides Azure database cost optimization recommendations."""

    def __init__(self):
        """Initialize the Database Agent with Azure AI Agents client."""
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

        # Create the database optimization agent with function tools
        self.agent = self.client.create_agent(
            model=os.environ['MODEL_DEPLOYMENT_NAME'],
            name='foundry-database-agent',
            instructions="""You are an Azure database cost optimization specialist.

You help users optimize their Azure SQL databases and Cosmos DB accounts by:
1. Analyzing database configurations and usage patterns
2. Identifying underutilized or overprovisioned databases
3. Recommending elastic pool consolidation opportunities
4. Analyzing Cosmos DB multi-region and throughput settings
5. Providing specific cost-saving recommendations with estimated savings

When analyzing databases:
- Focus on SQL tier optimization (Basic, Standard, Premium, General Purpose, Business Critical)
- Identify elastic pool opportunities for multiple standalone databases
- Review Cosmos DB region replication and write configurations
- Consider auto-pause for dev/test databases
- Recommend appropriate consistency levels for Cosmos DB

Always provide actionable recommendations with estimated monthly cost impacts.
Be specific about which databases or accounts need attention and why.

Always use the functions to get real data before providing recommendations.""",
            tools=DATABASE_TOOLS,
        )
        logger.info(f"Database Agent created with ID: {self.agent.id}")
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
                logger.info(f"Database Agent: Executing {len(tool_calls)} function call(s)")

                tool_outputs = []
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    logger.info(f"Calling function: {function_name}")

                    # Execute the appropriate function
                    try:
                        if function_name == 'list_sql_databases':
                            result = list_sql_databases()
                        elif function_name == 'analyze_sql_elastic_pools':
                            result = analyze_sql_elastic_pools()
                        elif function_name == 'list_cosmos_db_accounts':
                            result = list_cosmos_db_accounts()
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
            logger.error(f'Database Agent: Run failed - {run.last_error}')
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


async def create_foundry_database_agent() -> DatabaseAgent:
    """Create and return a database agent instance."""
    agent = DatabaseAgent()
    await agent.create_agent()
    return agent
