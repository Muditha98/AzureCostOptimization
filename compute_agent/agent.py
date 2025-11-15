""" Azure AI Foundry Agent that analyzes Azure VM compute resources and provides optimization recommendations """

import os
import logging
import json
from azure.ai.agents import AgentsClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import Agent, ListSortOrder, MessageRole
from compute_agent.azure_helpers import get_vm_metrics, list_vms, get_vm_right_sizing_recommendations

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Function tool definitions for Azure VM analysis
COMPUTE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_vm_metrics",
            "description": "Get CPU, memory, and disk metrics for Azure VMs from Azure Monitor. Returns utilization data, costs, and optimization recommendations.",
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
                    },
                    "vm_name": {
                        "type": "string",
                        "description": "VM name to analyze (optional, analyzes all VMs if not specified)"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back for metrics (default 7)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_vms",
            "description": "List all virtual machines in the Azure subscription with basic information including size, location, OS type, and monthly costs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subscription_id": {
                        "type": "string",
                        "description": "Azure subscription ID (optional, uses default from environment)"
                    },
                    "resource_group": {
                        "type": "string",
                        "description": "Resource group filter (optional, lists all VMs if not specified)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_vm_right_sizing_recommendations",
            "description": "Analyze VM utilization and provide detailed right-sizing recommendations with implementation steps, savings calculations, and risk assessments.",
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
                    "vm_name": {
                        "type": "string",
                        "description": "VM name (optional)"
                    },
                    "cpu_threshold": {
                        "type": "number",
                        "description": "CPU utilization threshold percentage below which to recommend downsizing (default 20.0)"
                    }
                }
            }
        }
    }
]

class ComputeAgent:

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

        # Create the compute optimization agent with function tools
        self.agent = self.client.create_agent(
            model=os.environ['MODEL_DEPLOYMENT_NAME'],
            name='foundry-compute-agent',
            instructions="""
            You are an Azure Compute Optimization specialist. Your expertise is analyzing Azure Virtual Machines (VMs) for optimization opportunities.

            **Your Capabilities:**
            You have access to three powerful functions to analyze real Azure subscription data:

            1. `get_vm_metrics` - Get real VM CPU/memory utilization metrics from Azure Monitor
            2. `list_vms` - List all VMs with costs in the subscription
            3. `get_vm_right_sizing_recommendations` - Get detailed right-sizing recommendations

            **When analyzing VMs:**
            - Always call the appropriate function to get real Azure data
            - Analyze CPU utilization patterns over the monitoring period
            - Identify underutilized VMs (<20% average CPU)
            - Calculate actual cost savings potential
            - Provide specific, actionable recommendations

            **Recommendation Priorities:**
            - HIGH: CPU <10% - Severe underutilization, major savings opportunity
            - MEDIUM: CPU 10-20% - Clear underutilization, good savings potential
            - LOW: CPU 20-40% - Some headroom, monitor before action
            - OPTIMAL: CPU >40% - Well-sized, no action needed

            **Your Responses Should:**
            - Be data-driven with specific metrics and costs
            - Include VM names, sizes, and resource groups
            - Provide implementation steps with Azure CLI commands
            - Estimate downtime and risk levels
            - Calculate both monthly and annual savings

            Always use the functions to get real data before providing recommendations. Never make up metrics or costs.
            """,
            tools=COMPUTE_TOOLS,
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
            import time
            time.sleep(0.5)

            # Get the latest run status
            run = self.client.runs.get(thread_id=thread.id, run_id=run.id)

            # Handle function calls
            if run.status == 'requires_action':
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                logger.info(f"Compute Agent: Executing {len(tool_calls)} function call(s)")

                tool_outputs = []
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    logger.info(f"Calling function: {function_name} with args: {function_args}")

                    # Execute the appropriate function
                    try:
                        if function_name == 'get_vm_metrics':
                            result = await get_vm_metrics(**function_args)
                        elif function_name == 'list_vms':
                            result = await list_vms(**function_args)
                        elif function_name == 'get_vm_right_sizing_recommendations':
                            result = await get_vm_right_sizing_recommendations(**function_args)
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
            logger.error(f'Compute Agent: Run failed - {run.last_error}')
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

async def create_foundry_compute_agent() -> ComputeAgent:
    """Factory function to create and initialize the Compute Agent"""
    agent = ComputeAgent()
    await agent.create_agent()
    return agent
