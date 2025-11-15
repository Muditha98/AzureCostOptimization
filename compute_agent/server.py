import os
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from compute_agent.agent_executor import create_foundry_agent_executor

load_dotenv()

host = os.environ["SERVER_URL"]
port = os.environ["COMPUTE_AGENT_PORT"]

# Define agent skills
skills = [
    AgentSkill(
        id='analyze_vm_metrics',
        name='Analyze VM Performance Metrics',
        description='Analyzes real Azure VM CPU and memory utilization from Azure Monitor to identify optimization opportunities',
        tags=['compute', 'vm', 'metrics', 'azure', 'monitoring'],
        examples=[
            'Analyze CPU utilization for all VMs in my subscription',
            'Show me underutilized VMs in the production resource group',
            'Get performance metrics for VMs over the last 7 days',
        ],
    ),
    AgentSkill(
        id='vm_right_sizing',
        name='VM Right-Sizing Recommendations',
        description='Provides detailed right-sizing recommendations with cost savings, implementation steps, and risk assessments',
        tags=['compute', 'vm', 'rightsizing', 'cost', 'optimization'],
        examples=[
            'Recommend VM size optimizations for underutilized instances',
            'Show me which VMs can be downsized to save money',
            'Get right-sizing recommendations with implementation steps',
        ],
    ),
    AgentSkill(
        id='list_vm_inventory',
        name='List VM Inventory',
        description='Lists all Azure VMs with sizes, locations, and monthly cost estimates',
        tags=['compute', 'vm', 'inventory', 'cost'],
        examples=[
            'List all VMs in my subscription with costs',
            'Show me VM inventory in the production resource group',
            'What VMs do I have running and what are their costs?',
        ],
    ),
]

# Create agent card
agent_card = AgentCard(
    name='Azure Compute Optimization Agent',
    description='Specialized agent for Azure Virtual Machine (VM) optimization powered by Azure AI Foundry. '
    'I connect to your Azure subscription to analyze real VM performance metrics from Azure Monitor. '
    'I identify underutilized VMs, provide right-sizing recommendations with cost savings calculations, '
    'and deliver implementation steps with Azure CLI commands. Expertise includes CPU/memory analysis, '
    'cost estimation, and risk assessment for VM optimization.',
    url=f'http://{host}:{port}/',
    version='1.0.0',
    default_input_modes=['text'],
    default_output_modes=['text'],
    capabilities=AgentCapabilities(streaming=True),
    skills=skills,
)

# Create agent executor
agent_executor = create_foundry_agent_executor(agent_card)

# Create request handler
request_handler = DefaultRequestHandler(
    agent_executor=agent_executor, task_store=InMemoryTaskStore()
)

# Create A2A application
a2a_app = A2AStarletteApplication(
    agent_card=agent_card, http_handler=request_handler
)

# Get routes
routes = a2a_app.routes()

# Add health check endpoint
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse('Azure Compute Optimization Agent is running!')

routes.append(Route(path='/health', methods=['GET'], endpoint=health_check))

# Create Starlette app
app = Starlette(routes=routes)

def main():
    # Run the server
    uvicorn.run(app, host=host, port=port)

if __name__ == '__main__':
    main()

