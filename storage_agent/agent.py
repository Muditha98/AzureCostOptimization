""" Azure AI Foundry Agent that analyzes Azure Storage resources and provides optimization recommendations """

import os
import logging
import json
import time
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import Agent, ListSortOrder, MessageRole
from storage_agent.azure_helpers import list_unattached_disks, get_storage_account_usage, analyze_blob_tiers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Function tool definitions for Azure Storage analysis
STORAGE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_unattached_disks",
            "description": "List all unattached managed disks that are costing money but not in use. Returns disk details, costs, and delete commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subscription_id": {
                        "type": "string",
                        "description": "Azure subscription ID (optional, uses default from environment if not specified)"
                    },
                    "resource_group": {
                        "type": "string",
                        "description": "Resource group name (optional, analyzes all resource groups if not specified)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_storage_account_usage",
            "description": "Analyze storage accounts for optimization opportunities including SKU recommendations and cost savings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subscription_id": {
                        "type": "string",
                        "description": "Azure subscription ID (optional, uses default from environment)"
                    },
                    "resource_group": {
                        "type": "string",
                        "description": "Resource group name (optional)"
                    },
                    "storage_account_name": {
                        "type": "string",
                        "description": "Storage account name to analyze (optional)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_blob_tiers",
            "description": "Analyze blob storage tiers and provide recommendations for moving data to cheaper tiers (Cool/Archive) to reduce costs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subscription_id": {
                        "type": "string",
                        "description": "Azure subscription ID (optional, uses default from environment)"
                    },
                    "resource_group": {
                        "type": "string",
                        "description": "Resource group name (optional)"
                    },
                    "storage_account_name": {
                        "type": "string",
                        "description": "Storage account name to analyze (optional)"
                    }
                }
            }
        }
    }
]

class StorageAgent:

    def __init__(self):

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

        # Create the storage optimization agent with function tools
        self.agent = self.client.create_agent(
            model=os.environ['MODEL_DEPLOYMENT_NAME'],
            name='foundry-storage-agent',
            instructions="""
            You are an Azure Storage Optimization specialist. Your expertise is analyzing Azure storage resources for cost savings.

            **Your Capabilities:**
            You have access to three powerful functions to analyze real Azure subscription data:

            1. `list_unattached_disks` - Find managed disks not attached to any VM (wasted money)
            2. `get_storage_account_usage` - Analyze storage accounts for SKU optimization
            3. `analyze_blob_tiers` - Recommend blob tier changes (Hot → Cool → Archive)

            **Focus Areas:**
            - Unattached managed disks costing money with no benefit
            - Overprovisioned storage accounts (Premium when Standard works)
            - Unnecessary geo-redundancy (GRS when LRS is sufficient)
            - Blob storage tier optimization (move cold data to cheaper tiers)
            - Old snapshots and blob versions consuming storage

            **When analyzing storage:**
            - Always call the appropriate function to get real Azure data
            - Identify unattached disks older than 30 days (high priority waste)
            - Check if Premium storage is necessary
            - Recommend lifecycle policies for blob tier management
            - Calculate actual savings in dollars per month and per year

            **Your Responses Should:**
            - Be data-driven with specific disk names, sizes, and costs
            - Include delete commands for unattached disks
            - Provide SKU change recommendations with cost impact
            - Suggest lifecycle management policies for blob storage
            - Calculate both monthly and annual savings
            - Assess priority (HIGH for old unattached disks, MEDIUM for SKU changes)

            Always use the functions to get real data before providing recommendations. Never make up metrics or costs.
            """,
            tools=STORAGE_TOOLS,
        )
        return self.agent

    async def run_conversation(self, user_message: str) -> list[str]:
        if not self.agent:
            await self.create_agent()

        # Create a thread for the chat session
        thread = self.client.threads.create()

        # Send user message
        self.client.messages.create(thread_id=thread.id, role=MessageRole.USER, content=user_message)

        # Create a run (not create_and_process, we need to handle function calls)
        run = self.client.runs.create(thread_id=thread.id, agent_id=self.agent.id)

        # Function calling loop - poll until completion
        while run.status in ['queued', 'in_progress', 'requires_action']:
            # Wait a bit before polling
            time.sleep(0.5)

            # Get the latest run status
            run = self.client.runs.get(thread_id=thread.id, run_id=run.id)

            # Handle function calls
            if run.status == 'requires_action':
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                logger.info(f"Storage Agent: Executing {len(tool_calls)} function call(s)")

                tool_outputs = []
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    logger.info(f"Calling function: {function_name} with args: {function_args}")

                    # Execute the appropriate function
                    try:
                        if function_name == 'list_unattached_disks':
                            result = await list_unattached_disks(**function_args)
                        elif function_name == 'get_storage_account_usage':
                            result = await get_storage_account_usage(**function_args)
                        elif function_name == 'analyze_blob_tiers':
                            result = await analyze_blob_tiers(**function_args)
                        else:
                            result = {"error": f"Unknown function: {function_name}"}

                        logger.info(f"Function {function_name} completed successfully")

                        tool_outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": json.dumps(result)
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
            logger.error(f'Storage Agent: Run failed - {run.last_error}')
            return [f'Error: {run.last_error}']

        # Get response messages
        messages = self.client.messages.list(thread_id=thread.id, order=ListSortOrder.DESCENDING)
        responses = []
        for msg in messages:
            # Only get the latest assistant response
            if msg.role == 'assistant' and msg.text_messages:
                for text_msg in msg.text_messages:
                    responses.append(text_msg.text.value)
                break

        return responses if responses else ['No response received']

async def create_foundry_storage_agent() -> StorageAgent:
    """Factory function to create and initialize the Storage Agent"""
    agent = StorageAgent()
    await agent.create_agent()
    return agent
