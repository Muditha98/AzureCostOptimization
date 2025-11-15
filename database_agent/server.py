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
from database_agent.agent_executor import create_foundry_agent_executor

load_dotenv()

host = os.environ["SERVER_URL"]
port = os.environ["DATABASE_AGENT_PORT"]

# Define agent skills
skills = [
    AgentSkill(
        id='list_sql_databases',
        name='List SQL Databases',
        description='Lists all Azure SQL servers and databases with tier, DTU/vCore configuration, and monthly cost estimates',
        tags=['database', 'sql', 'inventory', 'cost'],
        examples=[
            'List all SQL databases in my subscription',
            'Show me SQL database inventory with costs',
            'What SQL databases do I have and their pricing tiers?',
        ],
    ),
    AgentSkill(
        id='analyze_sql_elastic_pools',
        name='Analyze SQL Elastic Pool Opportunities',
        description='Analyzes SQL databases to identify elastic pool consolidation opportunities for cost savings',
        tags=['database', 'sql', 'elastic-pool', 'optimization', 'cost'],
        examples=[
            'Can I save money by using elastic pools?',
            'Analyze elastic pool consolidation opportunities',
            'Which SQL databases should be consolidated into elastic pools?',
        ],
    ),
    AgentSkill(
        id='list_cosmos_db_accounts',
        name='List Cosmos DB Accounts',
        description='Lists all Cosmos DB accounts with throughput configuration, consistency levels, and multi-region settings',
        tags=['database', 'cosmosdb', 'inventory', 'configuration'],
        examples=[
            'List all Cosmos DB accounts',
            'Show me Cosmos DB configurations and costs',
            'What are my Cosmos DB multi-region setups?',
        ],
    ),
]

# Create agent card
agent_card = AgentCard(
    name='Azure Database Optimization Agent',
    description='Specialized agent for Azure SQL Database and Cosmos DB optimization powered by Azure AI Foundry. '
    'I connect to your Azure subscription to analyze SQL database tiers, identify elastic pool consolidation '
    'opportunities, and review Cosmos DB throughput and multi-region configurations. Expertise includes '
    'SQL database right-sizing, elastic pool recommendations, Cosmos DB consistency optimization, and cost analysis.',
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
    return PlainTextResponse('Azure Database Optimization Agent is running!')

routes.append(Route(path='/health', methods=['GET'], endpoint=health_check))

# Create Starlette app
app = Starlette(routes=routes)

def main():
    # Run the server
    uvicorn.run(app, host=host, port=port)

if __name__ == '__main__':
    main()
