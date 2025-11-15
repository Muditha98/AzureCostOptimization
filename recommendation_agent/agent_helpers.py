"""
Recommendation Agent Helper Functions

This module provides functions to aggregate findings from specialized agents
and generate comprehensive cost optimization recommendations.
"""

import os
import json
import httpx
from typing import Dict, List, Any


async def call_agent(agent_url: str, message: str) -> Dict[str, Any]:
    """
    Call a specialized agent via A2A protocol.

    Args:
        agent_url: The base URL of the agent (e.g., http://localhost:10001)
        message: The message/query to send to the agent

    Returns:
        Dict containing the agent's response or error
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{agent_url}/run",
                json={"message": message}
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "failed",
                    "error": f"Agent returned status {response.status_code}"
                }

    except Exception as e:
        return {
            "status": "failed",
            "error": f"Failed to call agent: {str(e)}"
        }


def aggregate_compute_findings() -> str:
    """
    Aggregate compute optimization findings.
    This is a synchronous wrapper that returns query instructions.

    Returns:
        JSON string with query to send to compute agent
    """
    query = {
        "agent": "compute",
        "url": f"http://{os.environ.get('SERVER_URL', 'localhost')}:{os.environ.get('COMPUTE_AGENT_PORT', '10001')}",
        "message": "Provide a comprehensive analysis of all VMs focusing on: "
                   "1) Underutilized VMs that can be downsized, "
                   "2) Expensive VMs with low CPU usage, "
                   "3) Right-sizing opportunities with specific SKU recommendations."
    }
    return json.dumps(query)


def aggregate_storage_findings() -> str:
    """
    Aggregate storage optimization findings.

    Returns:
        JSON string with query to send to storage agent
    """
    query = {
        "agent": "storage",
        "url": f"http://{os.environ.get('SERVER_URL', 'localhost')}:{os.environ.get('STORAGE_AGENT_PORT', '10002')}",
        "message": "Provide a comprehensive analysis of storage resources focusing on: "
                   "1) All unattached disks wasting money, "
                   "2) Storage accounts that can be optimized, "
                   "3) Blob tier optimization opportunities."
    }
    return json.dumps(query)


def aggregate_database_findings() -> str:
    """
    Aggregate database optimization findings.

    Returns:
        JSON string with query to send to database agent
    """
    query = {
        "agent": "database",
        "url": f"http://{os.environ.get('SERVER_URL', 'localhost')}:{os.environ.get('DATABASE_AGENT_PORT', '10003')}",
        "message": "Provide a comprehensive analysis of database resources focusing on: "
                   "1) SQL databases that can be optimized or downsized, "
                   "2) Elastic pool consolidation opportunities, "
                   "3) Cosmos DB configuration and cost optimizations."
    }
    return json.dumps(query)


def aggregate_network_findings() -> str:
    """
    Aggregate network optimization findings.

    Returns:
        JSON string with query to send to network agent
    """
    query = {
        "agent": "network",
        "url": f"http://{os.environ.get('SERVER_URL', 'localhost')}:{os.environ.get('NETWORK_AGENT_PORT', '10004')}",
        "message": "Provide a comprehensive analysis of network resources focusing on: "
                   "1) All unattached public IPs, "
                   "2) Unused load balancers, "
                   "3) Unused network interfaces that can be cleaned up."
    }
    return json.dumps(query)


def aggregate_cost_findings() -> str:
    """
    Aggregate cost analysis findings.

    Returns:
        JSON string with query to send to cost analysis agent
    """
    query = {
        "agent": "cost_analysis",
        "url": f"http://{os.environ.get('SERVER_URL', 'localhost')}:{os.environ.get('COST_ANALYSIS_AGENT_PORT', '10005')}",
        "message": "Provide a comprehensive cost analysis including: "
                   "1) Current month spending by service, "
                   "2) Cost breakdown by resource group, "
                   "3) Cost trends showing any increases or decreases."
    }
    return json.dumps(query)


def generate_summary_report(agent_responses: Dict[str, Any]) -> str:
    """
    Generate a summary report from all agent responses.

    Args:
        agent_responses: Dict with keys like 'compute', 'storage', etc. and their responses

    Returns:
        JSON string with summary recommendations
    """
    try:
        summary = {
            "report_type": "Comprehensive Azure Cost Optimization Report",
            "generated_at": agent_responses.get("timestamp", ""),
            "sections": []
        }

        # Add each section if data is available
        if "compute" in agent_responses and agent_responses["compute"]:
            summary["sections"].append({
                "category": "Compute Optimization",
                "findings": agent_responses["compute"]
            })

        if "storage" in agent_responses and agent_responses["storage"]:
            summary["sections"].append({
                "category": "Storage Optimization",
                "findings": agent_responses["storage"]
            })

        if "database" in agent_responses and agent_responses["database"]:
            summary["sections"].append({
                "category": "Database Optimization",
                "findings": agent_responses["database"]
            })

        if "network" in agent_responses and agent_responses["network"]:
            summary["sections"].append({
                "category": "Network Optimization",
                "findings": agent_responses["network"]
            })

        if "cost_analysis" in agent_responses and agent_responses["cost_analysis"]:
            summary["sections"].append({
                "category": "Cost Analysis",
                "findings": agent_responses["cost_analysis"]
            })

        # Add high-level recommendations
        summary["high_level_recommendations"] = [
            "Review and implement quick wins from compute right-sizing (immediate impact)",
            "Delete unattached resources (disks, IPs, NICs) to eliminate waste",
            "Consider elastic pool consolidation for multiple SQL databases",
            "Monitor cost trends and set up Azure budgets for proactive cost management",
            "Implement tagging strategy for better cost allocation and tracking"
        ]

        return json.dumps(summary, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to generate summary: {str(e)}"})
