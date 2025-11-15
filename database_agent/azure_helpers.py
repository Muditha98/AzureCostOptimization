"""
Azure Database Optimization Helper Functions

This module provides functions to analyze Azure SQL and Cosmos DB resources
for cost optimization opportunities.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from shared.azure_clients import AzureClientManager


def list_sql_databases() -> str:
    """
    List all Azure SQL databases with utilization and cost information.

    Returns:
        JSON string containing SQL database details with recommendations.
    """
    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return json.dumps({"error": "AZURE_SUBSCRIPTION_ID not set in environment"})

        client_manager = AzureClientManager()
        sql_client = client_manager.get_sql_management_client(subscription_id)
        resource_client = client_manager.get_resource_management_client(subscription_id)

        databases_info = []

        # Get all SQL servers
        sql_servers = list(resource_client.resources.list(
            filter="resourceType eq 'Microsoft.Sql/servers'"
        ))

        if not sql_servers:
            return json.dumps({
                "message": "No Azure SQL servers found in subscription",
                "databases": []
            })

        for server_resource in sql_servers:
            try:
                # Parse resource group and server name from resource ID
                resource_parts = server_resource.id.split('/')
                resource_group = resource_parts[4]
                server_name = server_resource.name

                # List databases in this server
                databases = list(sql_client.databases.list_by_server(
                    resource_group_name=resource_group,
                    server_name=server_name
                ))

                for db in databases:
                    # Skip system database 'master'
                    if db.name.lower() == 'master':
                        continue

                    # Calculate estimated monthly cost based on SKU
                    estimated_cost = _calculate_sql_db_cost(db)

                    db_info = {
                        "name": db.name,
                        "server": server_name,
                        "resource_group": resource_group,
                        "location": db.location,
                        "sku": db.sku.name if db.sku else "Unknown",
                        "tier": db.sku.tier if db.sku else "Unknown",
                        "capacity": db.sku.capacity if db.sku else 0,
                        "max_size_gb": db.max_size_bytes / (1024**3) if db.max_size_bytes else 0,
                        "status": db.status,
                        "estimated_monthly_cost_usd": estimated_cost,
                        "creation_date": db.creation_date.isoformat() if db.creation_date else None,
                    }

                    # Add optimization recommendations
                    recommendations = []

                    if db.status and db.status.lower() == 'online':
                        if db.sku and db.sku.tier in ['Premium', 'BusinessCritical']:
                            recommendations.append(
                                "High-tier database detected. Consider downgrading to General Purpose "
                                "if premium features are not required."
                            )

                        if estimated_cost > 100:
                            recommendations.append(
                                f"High monthly cost (${estimated_cost:.2f}). Review database usage "
                                "and consider right-sizing or implementing auto-pause for dev/test databases."
                            )

                    elif db.status and db.status.lower() == 'paused':
                        recommendations.append(
                            "Database is paused. This is good for cost optimization. "
                            "You're only paying for storage."
                        )

                    db_info["recommendations"] = recommendations
                    databases_info.append(db_info)

            except Exception as e:
                # Log error but continue with other servers
                databases_info.append({
                    "server": server_resource.name,
                    "error": f"Failed to retrieve databases: {str(e)}"
                })

        result = {
            "total_databases": len([d for d in databases_info if "error" not in d]),
            "total_estimated_monthly_cost_usd": sum(
                d.get("estimated_monthly_cost_usd", 0)
                for d in databases_info if "error" not in d
            ),
            "databases": databases_info
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to list SQL databases: {str(e)}"})


def analyze_sql_elastic_pools() -> str:
    """
    Analyze SQL elastic pools and provide recommendations for cost optimization.

    Returns:
        JSON string with elastic pool analysis and recommendations.
    """
    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return json.dumps({"error": "AZURE_SUBSCRIPTION_ID not set in environment"})

        client_manager = AzureClientManager()
        sql_client = client_manager.get_sql_management_client(subscription_id)
        resource_client = client_manager.get_resource_management_client(subscription_id)

        pools_info = []

        # Get all SQL servers
        sql_servers = list(resource_client.resources.list(
            filter="resourceType eq 'Microsoft.Sql/servers'"
        ))

        if not sql_servers:
            return json.dumps({
                "message": "No Azure SQL servers found in subscription",
                "pools": []
            })

        standalone_databases = 0

        for server_resource in sql_servers:
            try:
                resource_parts = server_resource.id.split('/')
                resource_group = resource_parts[4]
                server_name = server_resource.name

                # List elastic pools
                pools = list(sql_client.elastic_pools.list_by_server(
                    resource_group_name=resource_group,
                    server_name=server_name
                ))

                # Count standalone databases (not in pools)
                databases = list(sql_client.databases.list_by_server(
                    resource_group_name=resource_group,
                    server_name=server_name
                ))

                for db in databases:
                    if db.name.lower() != 'master' and not db.elastic_pool_id:
                        standalone_databases += 1

                for pool in pools:
                    pool_info = {
                        "name": pool.name,
                        "server": server_name,
                        "resource_group": resource_group,
                        "location": pool.location,
                        "sku": pool.sku.name if pool.sku else "Unknown",
                        "tier": pool.sku.tier if pool.sku else "Unknown",
                        "capacity": pool.sku.capacity if pool.sku else 0,
                        "max_size_gb": pool.max_size_bytes / (1024**3) if pool.max_size_bytes else 0,
                        "per_database_settings": {
                            "min_capacity": pool.per_database_settings.min_capacity if pool.per_database_settings else 0,
                            "max_capacity": pool.per_database_settings.max_capacity if pool.per_database_settings else 0,
                        },
                        "estimated_monthly_cost_usd": _calculate_elastic_pool_cost(pool),
                    }

                    # Get databases in this pool
                    pool_databases = [
                        db.name for db in databases
                        if db.elastic_pool_id and pool.name in db.elastic_pool_id
                    ]
                    pool_info["databases_count"] = len(pool_databases)
                    pool_info["databases"] = pool_databases

                    # Recommendations
                    recommendations = []
                    if len(pool_databases) < 2:
                        recommendations.append(
                            f"Only {len(pool_databases)} database(s) in pool. "
                            "Elastic pools are most cost-effective with 2+ databases."
                        )

                    pool_info["recommendations"] = recommendations
                    pools_info.append(pool_info)

            except Exception as e:
                pools_info.append({
                    "server": server_resource.name,
                    "error": f"Failed to analyze pools: {str(e)}"
                })

        result = {
            "total_elastic_pools": len([p for p in pools_info if "error" not in p]),
            "standalone_databases": standalone_databases,
            "pools": pools_info,
            "general_recommendations": []
        }

        # Add general recommendation if multiple standalone DBs exist
        if standalone_databases >= 2:
            result["general_recommendations"].append(
                f"You have {standalone_databases} standalone databases. "
                "Consider consolidating them into elastic pools to reduce costs "
                "if they have similar performance requirements."
            )

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to analyze elastic pools: {str(e)}"})


def list_cosmos_db_accounts() -> str:
    """
    List all Cosmos DB accounts with throughput and cost analysis.

    Returns:
        JSON string with Cosmos DB account details and optimization recommendations.
    """
    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return json.dumps({"error": "AZURE_SUBSCRIPTION_ID not set in environment"})

        client_manager = AzureClientManager()
        cosmos_client = client_manager.get_cosmosdb_management_client(subscription_id)

        accounts_info = []

        # List all Cosmos DB accounts
        accounts = list(cosmos_client.database_accounts.list())

        if not accounts:
            return json.dumps({
                "message": "No Cosmos DB accounts found in subscription",
                "accounts": []
            })

        for account in accounts:
            try:
                # Parse resource group from account ID
                resource_parts = account.id.split('/')
                resource_group = resource_parts[4]

                account_info = {
                    "name": account.name,
                    "resource_group": resource_group,
                    "location": account.location,
                    "kind": account.kind,
                    "consistency_policy": account.consistency_policy.default_consistency_level if account.consistency_policy else "Unknown",
                    "locations": [loc.location_name for loc in account.locations] if account.locations else [],
                    "enable_automatic_failover": account.enable_automatic_failover,
                    "enable_multiple_write_locations": account.enable_multiple_write_locations,
                }

                # Estimate costs based on configuration
                estimated_cost = _calculate_cosmos_db_cost(account)
                account_info["estimated_monthly_cost_usd"] = estimated_cost

                # Recommendations
                recommendations = []

                if account.enable_multiple_write_locations:
                    recommendations.append(
                        "Multi-region writes enabled. This increases costs significantly. "
                        "Consider using single-region writes if high availability writes aren't required."
                    )

                if len(account.locations) > 2 if account.locations else False:
                    recommendations.append(
                        f"Account replicated to {len(account.locations)} regions. "
                        "Each additional region increases costs. Review if all regions are necessary."
                    )

                if account.consistency_policy and account.consistency_policy.default_consistency_level == "Strong":
                    recommendations.append(
                        "Strong consistency policy can impact performance and costs. "
                        "Consider using Session or Bounded Staleness if strong consistency isn't required."
                    )

                recommendations.append(
                    "Consider implementing autoscale throughput to automatically scale RU/s based on usage. "
                    "Also review serverless option for unpredictable or low-traffic workloads."
                )

                account_info["recommendations"] = recommendations
                accounts_info.append(account_info)

            except Exception as e:
                accounts_info.append({
                    "name": account.name,
                    "error": f"Failed to analyze account: {str(e)}"
                })

        result = {
            "total_accounts": len([a for a in accounts_info if "error" not in a]),
            "total_estimated_monthly_cost_usd": sum(
                a.get("estimated_monthly_cost_usd", 0)
                for a in accounts_info if "error" not in a
            ),
            "accounts": accounts_info
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to list Cosmos DB accounts: {str(e)}"})


# Helper functions for cost estimation

def _calculate_sql_db_cost(db) -> float:
    """Calculate estimated monthly cost for SQL database based on SKU."""
    if not db.sku:
        return 0.0

    # Rough cost estimates (actual costs vary by region and specific configuration)
    sku_costs = {
        "Basic": 5.0,
        "Standard": {
            "S0": 15.0, "S1": 30.0, "S2": 75.0, "S3": 150.0,
            "S4": 300.0, "S6": 600.0, "S7": 1200.0, "S9": 2400.0, "S12": 4800.0
        },
        "Premium": {
            "P1": 465.0, "P2": 930.0, "P4": 1860.0, "P6": 3720.0,
            "P11": 7000.0, "P15": 14000.0
        },
        "GeneralPurpose": 500.0,  # Varies widely based on vCores
        "BusinessCritical": 1500.0,  # Varies widely based on vCores
    }

    tier = db.sku.tier
    sku_name = db.sku.name

    if tier == "Basic":
        return sku_costs["Basic"]
    elif tier == "Standard" and isinstance(sku_costs["Standard"], dict):
        return sku_costs["Standard"].get(sku_name, 50.0)
    elif tier == "Premium" and isinstance(sku_costs["Premium"], dict):
        return sku_costs["Premium"].get(sku_name, 500.0)
    elif tier == "GeneralPurpose":
        # Estimate based on capacity (vCores)
        capacity = db.sku.capacity or 2
        return capacity * 250.0  # ~$250 per vCore per month
    elif tier == "BusinessCritical":
        # Estimate based on capacity (vCores)
        capacity = db.sku.capacity or 2
        return capacity * 750.0  # ~$750 per vCore per month

    return 0.0


def _calculate_elastic_pool_cost(pool) -> float:
    """Calculate estimated monthly cost for elastic pool based on SKU."""
    if not pool.sku:
        return 0.0

    tier = pool.sku.tier
    capacity = pool.sku.capacity or 0

    # Rough estimates
    if tier == "Standard":
        return capacity * 15.0  # ~$15 per 100 eDTU
    elif tier == "Premium":
        return capacity * 58.0  # ~$58 per 125 eDTU
    elif tier == "GeneralPurpose":
        return capacity * 250.0  # ~$250 per vCore
    elif tier == "BusinessCritical":
        return capacity * 750.0  # ~$750 per vCore

    return 0.0


def _calculate_cosmos_db_cost(account) -> float:
    """Calculate estimated monthly cost for Cosmos DB account."""
    # Base cost for single region (assuming 400 RU/s provisioned)
    base_cost = 24.0  # ~$24/month for 400 RU/s

    # Multiply by number of regions
    num_regions = len(account.locations) if account.locations else 1
    estimated_cost = base_cost * num_regions

    # Double cost if multi-region writes enabled
    if account.enable_multiple_write_locations:
        estimated_cost *= 2

    return estimated_cost
