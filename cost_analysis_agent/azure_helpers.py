"""
Azure Cost Analysis Helper Functions

This module provides functions to analyze Azure costs and spending patterns
using the Azure Cost Management API.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from shared.azure_clients import AzureClientManager


def get_current_month_costs() -> str:
    """
    Get current month's Azure costs with breakdown by service.

    Returns:
        JSON string containing current month cost summary.
    """
    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return json.dumps({"error": "AZURE_SUBSCRIPTION_ID not set in environment"})

        client_manager = AzureClientManager()
        cost_client = client_manager.get_cost_management_client(subscription_id)

        # Get current month date range
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1)
        if now.month == 12:
            end_date = datetime(now.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(now.year, now.month + 1, 1) - timedelta(days=1)

        # Build the scope for subscription-level query
        scope = f"/subscriptions/{subscription_id}"

        # Define query parameters for actual cost
        from azure.mgmt.costmanagement.models import (
            QueryDefinition,
            QueryDataset,
            QueryAggregation,
            QueryGrouping,
            TimeframeType,
            QueryTimePeriod,
            GranularityType
        )

        query_def = QueryDefinition(
            type="ActualCost",
            timeframe=TimeframeType.CUSTOM,
            time_period=QueryTimePeriod(
                from_property=start_date,
                to=end_date
            ),
            dataset=QueryDataset(
                granularity=GranularityType.DAILY,
                aggregation={
                    "totalCost": QueryAggregation(name="Cost", function="Sum")
                },
                grouping=[
                    QueryGrouping(type="Dimension", name="ServiceName")
                ]
            )
        )

        # Execute query
        try:
            query_result = cost_client.query.usage(scope=scope, parameters=query_def)
        except Exception as e:
            # If Cost Management API fails, provide helpful error
            if "SubscriptionNotFound" in str(e) or "not found" in str(e).lower():
                return json.dumps({
                    "error": "Cost Management API access error. This could be due to:",
                    "reasons": [
                        "Subscription is a free trial or MSDN subscription (Cost Management API may have limited access)",
                        "Insufficient permissions to access Cost Management data",
                        "Cost data not yet available for this subscription"
                    ],
                    "suggestion": "Verify subscription type and ensure you have Cost Management Reader role assigned."
                })
            else:
                raise e

        # Process results
        costs_by_service = {}
        total_cost = 0.0

        if query_result.rows:
            for row in query_result.rows:
                # Row format: [cost, service_name, date, currency]
                cost = float(row[0]) if len(row) > 0 else 0.0
                service_name = row[1] if len(row) > 1 else "Unknown"

                if service_name in costs_by_service:
                    costs_by_service[service_name] += cost
                else:
                    costs_by_service[service_name] = cost

                total_cost += cost

        # Sort services by cost (descending)
        sorted_services = sorted(
            costs_by_service.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Calculate percentages
        service_breakdown = []
        for service_name, cost in sorted_services:
            percentage = (cost / total_cost * 100) if total_cost > 0 else 0
            service_breakdown.append({
                "service": service_name,
                "cost_usd": round(cost, 2),
                "percentage": round(percentage, 1)
            })

        result = {
            "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            "total_cost_usd": round(total_cost, 2),
            "currency": "USD",
            "services_count": len(sorted_services),
            "top_services": service_breakdown[:10],  # Top 10 services
            "all_services": service_breakdown
        }

        # Add insights
        insights = []
        if total_cost > 0:
            if service_breakdown:
                top_service = service_breakdown[0]
                insights.append(
                    f"{top_service['service']} is the largest cost driver at "
                    f"${top_service['cost_usd']:.2f} ({top_service['percentage']:.1f}% of total)."
                )

            # Estimate monthly total based on days elapsed
            days_elapsed = (now - start_date).days + 1
            days_in_month = (end_date - start_date).days + 1
            if days_elapsed < days_in_month:
                projected_monthly_cost = (total_cost / days_elapsed) * days_in_month
                insights.append(
                    f"Based on {days_elapsed} days of data, projected month-end cost: "
                    f"${projected_monthly_cost:.2f}"
                )

        result["insights"] = insights

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to retrieve cost data: {str(e)}"})


def get_cost_by_resource_group() -> str:
    """
    Analyze costs broken down by resource group.

    Returns:
        JSON string with cost breakdown by resource group.
    """
    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return json.dumps({"error": "AZURE_SUBSCRIPTION_ID not set in environment"})

        client_manager = AzureClientManager()
        cost_client = client_manager.get_cost_management_client(subscription_id)

        # Get current month date range
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1)
        if now.month == 12:
            end_date = datetime(now.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(now.year, now.month + 1, 1) - timedelta(days=1)

        scope = f"/subscriptions/{subscription_id}"

        from azure.mgmt.costmanagement.models import (
            QueryDefinition,
            QueryDataset,
            QueryAggregation,
            QueryGrouping,
            TimeframeType,
            QueryTimePeriod,
            GranularityType
        )

        query_def = QueryDefinition(
            type="ActualCost",
            timeframe=TimeframeType.CUSTOM,
            time_period=QueryTimePeriod(
                from_property=start_date,
                to=end_date
            ),
            dataset=QueryDataset(
                granularity=GranularityType.DAILY,
                aggregation={
                    "totalCost": QueryAggregation(name="Cost", function="Sum")
                },
                grouping=[
                    QueryGrouping(type="Dimension", name="ResourceGroupName")
                ]
            )
        )

        try:
            query_result = cost_client.query.usage(scope=scope, parameters=query_def)
        except Exception as e:
            if "SubscriptionNotFound" in str(e) or "not found" in str(e).lower():
                return json.dumps({
                    "error": "Cost Management API access error",
                    "suggestion": "Verify subscription type and Cost Management Reader permissions."
                })
            else:
                raise e

        # Process results
        costs_by_rg = {}
        total_cost = 0.0

        if query_result.rows:
            for row in query_result.rows:
                cost = float(row[0]) if len(row) > 0 else 0.0
                rg_name = row[1] if len(row) > 1 else "Unknown"

                if rg_name in costs_by_rg:
                    costs_by_rg[rg_name] += cost
                else:
                    costs_by_rg[rg_name] = cost

                total_cost += cost

        # Sort by cost
        sorted_rgs = sorted(
            costs_by_rg.items(),
            key=lambda x: x[1],
            reverse=True
        )

        rg_breakdown = []
        for rg_name, cost in sorted_rgs:
            percentage = (cost / total_cost * 100) if total_cost > 0 else 0
            rg_breakdown.append({
                "resource_group": rg_name,
                "cost_usd": round(cost, 2),
                "percentage": round(percentage, 1)
            })

        result = {
            "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            "total_cost_usd": round(total_cost, 2),
            "resource_groups_count": len(sorted_rgs),
            "resource_groups": rg_breakdown
        }

        # Add recommendations
        recommendations = []
        if rg_breakdown:
            top_rg = rg_breakdown[0]
            recommendations.append(
                f"Focus optimization efforts on '{top_rg['resource_group']}' "
                f"(${top_rg['cost_usd']:.2f}, {top_rg['percentage']:.1f}% of total cost)."
            )

        # Identify small resource groups that could be consolidated
        small_rgs = [rg for rg in rg_breakdown if rg['cost_usd'] < 1.0]
        if len(small_rgs) > 3:
            recommendations.append(
                f"Consider consolidating {len(small_rgs)} resource groups with minimal costs "
                f"(< $1/month each) for better organization."
            )

        result["recommendations"] = recommendations

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to retrieve cost by resource group: {str(e)}"})


def get_cost_trends() -> str:
    """
    Analyze cost trends over the past 3 months.

    Returns:
        JSON string with cost trend analysis.
    """
    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return json.dumps({"error": "AZURE_SUBSCRIPTION_ID not set in environment"})

        client_manager = AzureClientManager()
        cost_client = client_manager.get_cost_management_client(subscription_id)

        # Get last 90 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)

        scope = f"/subscriptions/{subscription_id}"

        from azure.mgmt.costmanagement.models import (
            QueryDefinition,
            QueryDataset,
            QueryAggregation,
            TimeframeType,
            QueryTimePeriod,
            GranularityType
        )

        query_def = QueryDefinition(
            type="ActualCost",
            timeframe=TimeframeType.CUSTOM,
            time_period=QueryTimePeriod(
                from_property=start_date,
                to=end_date
            ),
            dataset=QueryDataset(
                granularity=GranularityType.DAILY,
                aggregation={
                    "totalCost": QueryAggregation(name="Cost", function="Sum")
                }
            )
        )

        try:
            query_result = cost_client.query.usage(scope=scope, parameters=query_def)
        except Exception as e:
            if "SubscriptionNotFound" in str(e) or "not found" in str(e).lower():
                return json.dumps({
                    "error": "Cost Management API access error",
                    "suggestion": "Verify subscription type and Cost Management Reader permissions."
                })
            else:
                raise e

        # Process daily costs
        daily_costs = []
        total_cost = 0.0

        if query_result.rows:
            for row in query_result.rows:
                cost = float(row[0]) if len(row) > 0 else 0.0
                date_value = row[1] if len(row) > 1 else None

                if date_value:
                    # Parse date (format: YYYYMMDD)
                    date_str = str(date_value)
                    try:
                        parsed_date = datetime.strptime(date_str, "%Y%m%d")
                        daily_costs.append({
                            "date": parsed_date.strftime("%Y-%m-%d"),
                            "cost": cost
                        })
                        total_cost += cost
                    except:
                        pass

        # Calculate average daily cost
        avg_daily_cost = total_cost / len(daily_costs) if daily_costs else 0

        # Group by month for trend analysis
        monthly_costs = {}
        for item in daily_costs:
            month_key = item["date"][:7]  # YYYY-MM
            if month_key in monthly_costs:
                monthly_costs[month_key] += item["cost"]
            else:
                monthly_costs[month_key] = item["cost"]

        monthly_breakdown = [
            {"month": month, "cost_usd": round(cost, 2)}
            for month, cost in sorted(monthly_costs.items())
        ]

        result = {
            "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            "total_cost_usd": round(total_cost, 2),
            "average_daily_cost_usd": round(avg_daily_cost, 2),
            "days_analyzed": len(daily_costs),
            "monthly_breakdown": monthly_breakdown
        }

        # Calculate trend
        insights = []
        if len(monthly_breakdown) >= 2:
            latest_month = monthly_breakdown[-1]
            previous_month = monthly_breakdown[-2]

            cost_change = latest_month["cost_usd"] - previous_month["cost_usd"]
            pct_change = (cost_change / previous_month["cost_usd"] * 100) if previous_month["cost_usd"] > 0 else 0

            if pct_change > 10:
                insights.append(
                    f"⚠️ Costs increased by {pct_change:.1f}% from {previous_month['month']} "
                    f"(${previous_month['cost_usd']:.2f}) to {latest_month['month']} "
                    f"(${latest_month['cost_usd']:.2f}). Investigate recent resource additions."
                )
            elif pct_change < -10:
                insights.append(
                    f"✓ Costs decreased by {abs(pct_change):.1f}% from {previous_month['month']} "
                    f"to {latest_month['month']}. Good cost management!"
                )
            else:
                insights.append(
                    f"Costs are relatively stable month-over-month ({pct_change:+.1f}% change)."
                )

        result["insights"] = insights

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to retrieve cost trends: {str(e)}"})
