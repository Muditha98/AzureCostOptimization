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
from network_agent.agent_executor import create_foundry_agent_executor

load_dotenv()

host = os.environ["SERVER_URL"]
port = os.environ["NETWORK_AGENT_PORT"]

# Define agent skills
skills = [
    AgentSkill(
        id='list_unattached_public_ips',
        name='List Unattached Public IPs',
        description='Identifies unattached public IP addresses that are incurring costs without being used',
        tags=['network', 'public-ip', 'waste', 'cost'],
        examples=[
            'Find unattached public IPs',
            'Show me unused public IP addresses',
            'Which public IPs are wasting money?',
        ],
    ),
    AgentSkill(
        id='analyze_load_balancers',
        name='Analyze Load Balancers',
        description='Analyzes load balancers for underutilization and identifies empty or idle load balancers',
        tags=['network', 'load-balancer', 'optimization', 'cost'],
        examples=[
            'Analyze my load balancers',
            'Which load balancers are underutilized?',
            'Find empty or idle load balancers',
        ],
    ),
    AgentSkill(
        id='analyze_network_interfaces',
        name='Analyze Network Interfaces',
        description='Analyzes network interfaces (NICs) and identifies unattached NICs that can be deleted',
        tags=['network', 'nic', 'cleanup', 'cost'],
        examples=[
            'Find unattached network interfaces',
            'Show me orphaned NICs',
            'Which network interfaces can be deleted?',
        ],
    ),
]

# Create agent card
agent_card = AgentCard(
    name='Azure Network Optimization Agent',
    description='Specialized agent for Azure network resource optimization powered by Azure AI Foundry. '
    'I connect to your Azure subscription to identify unattached public IPs, analyze load balancer utilization, '
    'and find orphaned network interfaces. Expertise includes network cost waste identification, '
    'resource cleanup recommendations, and network optimization strategies.',
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
    return PlainTextResponse('Azure Network Optimization Agent is running!')

routes.append(Route(path='/health', methods=['GET'], endpoint=health_check))

# Create Starlette app
app = Starlette(routes=routes)

def main():
    # Run the server
    uvicorn.run(app, host=host, port=port)

if __name__ == '__main__':
    main()
