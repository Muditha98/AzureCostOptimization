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
from storage_agent.agent_executor import create_foundry_agent_executor

load_dotenv()

host = os.environ["SERVER_URL"]
port = os.environ["STORAGE_AGENT_PORT"]

# Define agent skills
skills = [
    AgentSkill(
        id='find_unattached_disks',
        name='Find Unattached Disks',
        description='Identifies unattached managed disks wasting money with no benefit. Provides costs and delete commands.',
        tags=['storage', 'disks', 'waste', 'cost'],
        examples=[
            'Find all unattached disks in my subscription',
            'Show me disks not attached to any VM',
            'List idle disks costing me money',
        ],
    ),
    AgentSkill(
        id='storage_account_optimization',
        name='Storage Account Optimization',
        description='Analyzes storage accounts for SKU optimization, redundancy recommendations, and cost savings',
        tags=['storage', 'accounts', 'optimization', 'cost'],
        examples=[
            'Analyze my storage accounts for cost optimization',
            'Check if I need Premium storage or can use Standard',
            'Review storage account SKUs for savings',
        ],
    ),
    AgentSkill(
        id='blob_tier_optimization',
        name='Blob Tier Optimization',
        description='Recommends moving blob data to cheaper access tiers (Cool/Archive) and lifecycle policies',
        tags=['storage', 'blob', 'tiers', 'lifecycle'],
        examples=[
            'Recommend blob tier optimizations',
            'How can I save money on blob storage?',
            'Suggest lifecycle management policies for my blobs',
        ],
    ),
]

# Create agent card
agent_card = AgentCard(
    name='Azure Storage Optimization Agent',
    description='Specialized agent for Azure Storage optimization powered by Azure AI Foundry. '
    'I connect to your Azure subscription to analyze storage resources including managed disks, '
    'storage accounts, and blob storage. I identify unattached disks wasting money, recommend '
    'SKU downgrades (Premium → Standard, GRS → LRS), suggest blob tier changes (Hot → Cool → Archive), '
    'and provide lifecycle management policies. Expertise includes cost estimation and Azure CLI commands.',
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
    return PlainTextResponse('Azure Storage Optimization Agent is running!')

routes.append(Route(path='/health', methods=['GET'], endpoint=health_check))

# Create Starlette app
app = Starlette(routes=routes)

def main():
    # Run the server
    uvicorn.run(app, host=host, port=port)

if __name__ == '__main__':
    main()
