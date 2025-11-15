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
from recommendation_agent.agent_executor import create_foundry_agent_executor

load_dotenv()

host = os.environ["SERVER_URL"]
port = os.environ["RECOMMENDATION_AGENT_PORT"]

# Define agent skills
skills = [
    AgentSkill(
        id='aggregate_compute_findings',
        name='Aggregate Compute Findings',
        description='Aggregates VM optimization findings including right-sizing and performance analysis from the Compute Agent',
        tags=['recommendation', 'compute', 'aggregation'],
        examples=[
            'Get compute optimization summary',
            'What are the compute recommendations?',
        ],
    ),
    AgentSkill(
        id='aggregate_storage_findings',
        name='Aggregate Storage Findings',
        description='Aggregates storage optimization findings including disk, blob, and storage account recommendations from the Storage Agent',
        tags=['recommendation', 'storage', 'aggregation'],
        examples=[
            'Get storage optimization summary',
            'What are the storage recommendations?',
        ],
    ),
    AgentSkill(
        id='aggregate_database_findings',
        name='Aggregate Database Findings',
        description='Aggregates database optimization findings including SQL and Cosmos DB recommendations from the Database Agent',
        tags=['recommendation', 'database', 'aggregation'],
        examples=[
            'Get database optimization summary',
            'What are the database recommendations?',
        ],
    ),
    AgentSkill(
        id='aggregate_network_findings',
        name='Aggregate Network Findings',
        description='Aggregates network optimization findings including public IP, load balancer, and NIC cleanup from the Network Agent',
        tags=['recommendation', 'network', 'aggregation'],
        examples=[
            'Get network optimization summary',
            'What are the network recommendations?',
        ],
    ),
    AgentSkill(
        id='aggregate_cost_findings',
        name='Aggregate Cost Analysis Findings',
        description='Aggregates spending analysis and cost trends from the Cost Analysis Agent',
        tags=['recommendation', 'cost', 'aggregation'],
        examples=[
            'Get cost analysis summary',
            'What are the spending insights?',
        ],
    ),
    AgentSkill(
        id='generate_summary_report',
        name='Generate Comprehensive Summary Report',
        description='Creates a comprehensive, prioritized optimization roadmap aggregating all specialized agent findings',
        tags=['recommendation', 'summary', 'report', 'prioritization'],
        examples=[
            'Give me a comprehensive cost optimization report',
            'What are my top optimization opportunities?',
            'Create a prioritized optimization roadmap',
        ],
    ),
]

# Create agent card
agent_card = AgentCard(
    name='Azure Recommendation Orchestrator Agent',
    description='Master orchestrator agent that aggregates findings from all specialized Azure optimization agents '
    'powered by Azure AI Foundry. I coordinate with Compute, Storage, Database, Network, and Cost Analysis agents '
    'to provide a comprehensive, prioritized optimization strategy. Expertise includes cross-domain optimization, '
    'ROI prioritization, and creating actionable optimization roadmaps with quick wins and strategic initiatives.',
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
    return PlainTextResponse('Azure Recommendation Orchestrator Agent is running!')

routes.append(Route(path='/health', methods=['GET'], endpoint=health_check))

# Create Starlette app
app = Starlette(routes=routes)

def main():
    # Run the server
    uvicorn.run(app, host=host, port=port)

if __name__ == '__main__':
    main()
