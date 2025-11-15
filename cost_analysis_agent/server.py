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
from cost_analysis_agent.agent_executor import create_foundry_agent_executor

load_dotenv()

host = os.environ["SERVER_URL"]
port = os.environ["COST_ANALYSIS_AGENT_PORT"]

# Define agent skills
skills = [
    AgentSkill(
        id='get_current_month_costs',
        name='Current Month Cost Analysis',
        description='Analyzes current month Azure spending with detailed service-level breakdown to identify the biggest cost drivers',
        tags=['cost', 'spending', 'analysis', 'billing'],
        examples=[
            "What's my Azure spending this month?",
            'Show me current month costs by service',
            'Which Azure services cost the most?',
        ],
    ),
    AgentSkill(
        id='get_cost_by_resource_group',
        name='Resource Group Cost Analysis',
        description='Breaks down Azure costs by resource group to identify which environments or projects are most expensive',
        tags=['cost', 'resource-group', 'analysis', 'billing'],
        examples=[
            'Show costs by resource group',
            'Which resource groups are most expensive?',
            'Break down my spending by resource group',
        ],
    ),
    AgentSkill(
        id='get_cost_trends',
        name='Cost Trend Analysis',
        description='Analyzes spending trends over the past 3 months to identify cost increases, decreases, and spending patterns',
        tags=['cost', 'trends', 'analysis', 'forecasting'],
        examples=[
            'Show me cost trends over time',
            'Are my Azure costs increasing?',
            'Compare costs month-over-month',
        ],
    ),
]

# Create agent card
agent_card = AgentCard(
    name='Azure Cost Analysis Agent',
    description='Specialized agent for Azure cost analysis and spending insights powered by Azure AI Foundry. '
    'I connect to Azure Cost Management API to analyze your spending patterns, identify the biggest cost drivers, '
    'track cost trends over time, and provide insights into spending anomalies. Expertise includes service-level '
    'cost breakdown, resource group analysis, and trend forecasting.',
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
    return PlainTextResponse('Azure Cost Analysis Agent is running!')

routes.append(Route(path='/health', methods=['GET'], endpoint=health_check))

# Create Starlette app
app = Starlette(routes=routes)

def main():
    # Run the server
    uvicorn.run(app, host=host, port=port)

if __name__ == '__main__':
    main()
