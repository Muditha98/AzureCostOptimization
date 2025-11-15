# Azure Cost Optimization Multi-Agent System

An intelligent multi-agent system powered by Azure AI Foundry that analyzes your Azure infrastructure and provides comprehensive cost optimization recommendations using Agent-to-Agent (A2A) protocol.

## Overview

This system uses 6 specialized AI agents that work together to analyze different aspects of your Azure subscription:

1. **Compute Agent** - Analyzes VMs for right-sizing opportunities
2. **Storage Agent** - Reviews disks, blobs, and storage accounts for optimization
3. **Database Agent** - Examines SQL and Cosmos DB configurations
4. **Network Agent** - Identifies unused public IPs, load balancers, and NICs
5. **Cost Analysis Agent** - Provides spending insights and trend analysis
6. **Recommendation Agent** - Aggregates findings and creates prioritized action plans

All agents communicate via the **Routing Agent**, which intelligently delegates requests to the appropriate specialized agents using the A2A protocol.

## Architecture

```
┌─────────────────┐
│     Client      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Routing Agent   │ ◄──── Discovers agents via A2A Agent Cards
└────────┬────────┘
         │
         ├──────┬──────┬──────┬──────┬──────┐
         ▼      ▼      ▼      ▼      ▼      ▼
    ┌────┐  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
    │ CP │  │ ST │ │ DB │ │ NW │ │ CA │ │ RC │
    └─┬──┘  └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘ └─┬──┘
      │       │      │      │      │      │
      └───────┴──────┴──────┴──────┴──────┘
                     │
              Azure Subscription
```

**Legend:**
- CP: Compute Agent
- ST: Storage Agent
- DB: Database Agent
- NW: Network Agent
- CA: Cost Analysis Agent
- RC: Recommendation Agent

## Features

- **Real Azure Data Integration** - Connects to your Azure subscription via Azure SDK
- **AI-Powered Analysis** - Uses GPT-4o via Azure AI Foundry for intelligent recommendations
- **Agent-to-Agent (A2A) Protocol** - Standardized agent communication and discovery
- **Comprehensive Coverage** - Analyzes compute, storage, database, network, and cost data
- **Actionable Recommendations** - Provides Azure CLI commands for implementing changes
- **Cost Estimates** - Calculates potential monthly/annual savings
- **Prioritized Roadmap** - Ranks recommendations by ROI and effort

## Prerequisites

- Python 3.10+
- Azure subscription with resources to analyze
- Azure AI Foundry project with GPT-4o deployment
- Azure CLI (authenticated)

## Installation

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd 06-build-remote-agents-with-a2a/python
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and configure:

```bash
# Azure AI Foundry Configuration
PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project-id"
MODEL_DEPLOYMENT_NAME="gpt-4o"

# Azure Subscription
AZURE_SUBSCRIPTION_ID="your-subscription-id"
```

### 5. Authenticate with Azure

```bash
# Login to Azure
az login

# Login to Azure AI (required for AI Foundry)
az login --scope "https://ai.azure.com/.default"
```

## Usage

### Start the Multi-Agent System

Run all agents and the client:

```bash
python run_all.py
```

This will:
1. Start all 6 specialized agents on ports 10001-10006
2. Start the routing agent on port 10009
3. Launch the interactive client

### Example Queries

Once the client starts, you can ask questions like:

**Compute Optimization:**
```
Analyze my VMs and suggest right-sizing opportunities
Which VMs are underutilized and can be downsized?
```

**Storage Optimization:**
```
Find unattached disks in my subscription
Which storage accounts can be optimized?
Analyze blob storage tier recommendations
```

**Database Optimization:**
```
Review my SQL databases for cost savings
Can I consolidate databases into elastic pools?
Analyze Cosmos DB multi-region configurations
```

**Network Optimization:**
```
Find unused public IP addresses
Which load balancers are empty or underutilized?
Show me orphaned network interfaces
```

**Cost Analysis:**
```
What's my Azure spending this month?
Show cost trends over the last 3 months
Which resource groups cost the most?
```

**Comprehensive Analysis:**
```
Give me a complete cost optimization report
What are my top 10 optimization opportunities?
Create a prioritized optimization roadmap
```

## Project Structure

```
.
├── README.md                       # This file
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variables template
├── .gitignore                      # Git ignore rules
├── run_all.py                      # Launches all agents and client
├── client.py                       # Interactive client
│
├── compute_agent/                  # VM optimization agent
│   ├── agent.py                    # Azure AI agent logic
│   ├── agent_executor.py           # A2A executor
│   ├── azure_helpers.py            # Azure API integration
│   └── server.py                   # HTTP server
│
├── storage_agent/                  # Storage optimization agent
│   ├── agent.py
│   ├── agent_executor.py
│   ├── azure_helpers.py
│   └── server.py
│
├── database_agent/                 # Database optimization agent
│   ├── agent.py
│   ├── agent_executor.py
│   ├── azure_helpers.py
│   └── server.py
│
├── network_agent/                  # Network optimization agent
│   ├── agent.py
│   ├── agent_executor.py
│   ├── azure_helpers.py
│   └── server.py
│
├── cost_analysis_agent/            # Cost analysis agent
│   ├── agent.py
│   ├── agent_executor.py
│   ├── azure_helpers.py
│   └── server.py
│
├── recommendation_agent/           # Recommendation aggregation agent
│   ├── agent.py
│   ├── agent_executor.py
│   ├── agent_helpers.py
│   └── server.py
│
├── routing_agent/                  # Master routing agent
│   ├── agent.py
│   └── server.py
│
└── shared/                         # Shared utilities
    ├── __init__.py
    └── azure_clients.py            # Azure SDK client management
```

## How It Works

### 1. Agent Discovery

The routing agent discovers specialized agents via A2A protocol:
- Each agent exposes an Agent Card at `/.well-known/agent-card.json`
- Agent Cards describe capabilities, skills, and endpoints
- Routing agent fetches cards on startup to learn about available agents

### 2. Request Routing

When you ask a question:
1. Client sends request to Routing Agent
2. Routing Agent uses GPT-4o to determine which specialized agent(s) to call
3. Routing Agent forwards request to appropriate agent(s)
4. Specialized agent(s) execute Azure SDK calls to gather data
5. GPT-4o analyzes data and generates recommendations
6. Response flows back through Routing Agent to Client

### 3. Azure Data Access

Each specialized agent:
- Uses Azure SDK Python packages to query Azure Resource Manager
- Authenticates via Azure CLI credentials (DefaultAzureCredential)
- Queries real subscription data (VMs, disks, databases, etc.)
- Analyzes metrics from Azure Monitor where applicable

### 4. AI-Powered Analysis

Each agent uses Azure AI Foundry (GPT-4o) with function calling:
- Agent defines function tools for Azure API operations
- GPT-4o decides which functions to call based on user query
- Functions execute and return real Azure data
- GPT-4o synthesizes findings into actionable recommendations

## Azure Permissions Required

Your Azure identity needs these permissions:

- **Reader** role on subscription (to query resources)
- **Monitoring Reader** role (for Azure Monitor metrics)
- **Cost Management Reader** role (for cost data)

Grant permissions:

```bash
SUBSCRIPTION_ID="your-subscription-id"
USER_EMAIL="your-email@domain.com"

az role assignment create \
  --assignee $USER_EMAIL \
  --role "Reader" \
  --scope /subscriptions/$SUBSCRIPTION_ID

az role assignment create \
  --assignee $USER_EMAIL \
  --role "Monitoring Reader" \
  --scope /subscriptions/$SUBSCRIPTION_ID

az role assignment create \
  --assignee $USER_EMAIL \
  --role "Cost Management Reader" \
  --scope /subscriptions/$SUBSCRIPTION_ID
```

## Azure AI Foundry Setup

### 1. Create Azure AI Foundry Project

```bash
# Create resource group
az group create --name my-ai-foundry-rg --location westus3

# Create AI Foundry hub (requires Azure portal currently)
# Visit: https://ai.azure.com
# Create new project and deploy gpt-4o model
```

### 2. Get Project Endpoint

1. Go to https://ai.azure.com
2. Select your project
3. Go to Settings → Overview
4. Copy the **Project Connection String** (endpoint URL)

### 3. Deploy GPT-4o Model

1. In Azure AI Studio, go to Deployments
2. Create new deployment
3. Select `gpt-4o` model
4. Note the deployment name (e.g., "gpt-4o")

## Troubleshooting

### Authentication Issues

If you see MFA expiration errors:

```bash
az logout
az login --tenant "your-tenant-id" --scope "https://ai.azure.com/.default"
```

### Port Already in Use

If ports are occupied:

```bash
# Kill processes using agent ports (Windows)
netstat -ano | findstr :10001
taskkill /PID <process-id> /F

# Kill processes (Linux/Mac)
lsof -ti:10001 | xargs kill -9
```

### Import Errors

Ensure you're in the virtual environment:

```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Development

### Running Individual Agents

You can run agents separately for testing:

```bash
# Start compute agent only
uvicorn compute_agent.server:app --host localhost --port 10001
```

### Testing Agent Cards

Verify A2A agent card endpoints:

```bash
curl http://localhost:10001/.well-known/agent-card.json
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - See LICENSE file for details

## Acknowledgments

- Built with [Azure AI Foundry](https://azure.microsoft.com/en-us/products/ai-studio/)
- Uses [Azure SDK for Python](https://github.com/Azure/azure-sdk-for-python)
- Implements [A2A Protocol](https://github.com/anthropics/anthropic-agent-to-agent)

## Support

For issues and questions:
- Create an issue in this repository
- Check Azure AI Foundry documentation: https://learn.microsoft.com/azure/ai-studio/
- Azure SDK Python docs: https://learn.microsoft.com/python/api/overview/azure/

## Roadmap

- [ ] Add support for Azure Kubernetes Service (AKS) optimization
- [ ] Implement caching for Azure resource queries
- [ ] Add web UI for visualization
- [ ] Export recommendations to Excel/PDF
- [ ] Add email notifications for high-impact findings
- [ ] Implement recommendation tracking and history
