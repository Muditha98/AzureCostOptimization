""" Azure API helper functions for Storage Optimization Agent """

import logging
import json
from datetime import datetime, timedelta
from shared import azure_clients, calculate_disk_cost, format_cost

logger = logging.getLogger(__name__)


async def list_unattached_disks(subscription_id: str = None, resource_group: str = None) -> dict:
    """
    List all unattached managed disks (idle disks costing money)

    Args:
        subscription_id: Azure subscription ID (optional, uses default from env)
        resource_group: Resource group name (optional, all RGs if not specified)

    Returns:
        dict with unattached disk data and cost savings potential
    """
    try:
        sub_id = subscription_id or azure_clients.subscription_id
        if not sub_id:
            return {"error": "AZURE_SUBSCRIPTION_ID not configured"}

        compute_client = azure_clients.get_compute_client(sub_id)

        # List all managed disks
        if resource_group:
            disks = list(compute_client.disks.list_by_resource_group(resource_group))
        else:
            disks = list(compute_client.disks.list())

        unattached_disks = []
        total_wasted_cost = 0

        for disk in disks:
            # Check if disk is not attached to any VM
            if disk.managed_by is None:
                # Calculate monthly cost
                monthly_cost = calculate_disk_cost(disk.sku.name, disk.disk_size_gb)
                total_wasted_cost += monthly_cost

                # Calculate age
                age_days = (datetime.utcnow() - disk.time_created).days if disk.time_created else 0

                unattached_disks.append({
                    'name': disk.name,
                    'resource_group': disk.id.split('/')[4],
                    'location': disk.location,
                    'size_gb': disk.disk_size_gb,
                    'sku': disk.sku.name,
                    'monthly_cost': monthly_cost,
                    'monthly_cost_formatted': format_cost(monthly_cost),
                    'age_days': age_days,
                    'created_date': disk.time_created.isoformat() if disk.time_created else 'Unknown',
                    'recommendation': f"Delete this unattached disk to save {format_cost(monthly_cost)}/month" if age_days > 30
                                     else "Verify if disk is still needed (recently created)",
                    'priority': 'HIGH' if age_days > 90 else 'MEDIUM' if age_days > 30 else 'LOW',
                    'delete_command': f"az disk delete --resource-group {disk.id.split('/')[4]} --name {disk.name} --yes"
                })

        return {
            'subscription_id': sub_id,
            'total_disks_scanned': len(disks),
            'unattached_disks_count': len(unattached_disks),
            'total_monthly_waste': round(total_wasted_cost, 2),
            'total_monthly_waste_formatted': format_cost(total_wasted_cost),
            'total_annual_waste': round(total_wasted_cost * 12, 2),
            'total_annual_waste_formatted': format_cost(total_wasted_cost * 12),
            'unattached_disks': unattached_disks
        }

    except Exception as e:
        logger.error(f"Error in list_unattached_disks: {e}", exc_info=True)
        return {"error": str(e)}


async def get_storage_account_usage(subscription_id: str = None, resource_group: str = None,
                                     storage_account_name: str = None) -> dict:
    """
    Get storage account usage and analyze for optimization opportunities

    Args:
        subscription_id: Azure subscription ID (optional)
        resource_group: Resource group name (optional)
        storage_account_name: Storage account name (optional)

    Returns:
        dict with storage account usage and recommendations
    """
    try:
        sub_id = subscription_id or azure_clients.subscription_id
        if not sub_id:
            return {"error": "AZURE_SUBSCRIPTION_ID not configured"}

        storage_client = azure_clients.get_storage_client(sub_id)

        # List storage accounts
        if resource_group:
            accounts = list(storage_client.storage_accounts.list_by_resource_group(resource_group))
        else:
            accounts = list(storage_client.storage_accounts.list())

        # Filter by name if provided
        if storage_account_name:
            accounts = [acc for acc in accounts if acc.name.lower() == storage_account_name.lower()]

        if not accounts:
            return {"message": "No storage accounts found", "accounts": []}

        results = []

        for account in accounts:
            try:
                # Get account properties
                account_props = storage_client.storage_accounts.get_properties(
                    account.id.split('/')[4],  # resource_group
                    account.name
                )

                # Estimate costs based on SKU (simplified)
                sku_name = account_props.sku.name
                estimated_cost = _estimate_storage_cost(sku_name, account_props.primary_endpoints)

                # Analyze for optimization
                recommendations = []
                potential_savings = 0

                # Check if using premium when standard might work
                if 'Premium' in sku_name:
                    recommendations.append("Consider downgrading from Premium to Standard storage if high IOPS not needed")
                    potential_savings = estimated_cost * 0.3  # 30% savings estimate

                # Check if using GRS when LRS might work
                if 'GRS' in sku_name or 'RAGRS' in sku_name:
                    recommendations.append("Consider using LRS instead of GRS if geo-redundancy not critical")
                    potential_savings += estimated_cost * 0.2  # 20% additional savings

                if not recommendations:
                    recommendations.append("Storage account appears optimally configured")

                results.append({
                    'name': account.name,
                    'resource_group': account.id.split('/')[4],
                    'location': account.location,
                    'sku': sku_name,
                    'kind': account.kind,
                    'access_tier': account_props.access_tier if hasattr(account_props, 'access_tier') else 'N/A',
                    'estimated_monthly_cost': round(estimated_cost, 2),
                    'estimated_monthly_cost_formatted': format_cost(estimated_cost),
                    'recommendations': recommendations,
                    'potential_monthly_savings': round(potential_savings, 2),
                    'potential_savings_formatted': format_cost(potential_savings),
                    'primary_endpoints': {
                        'blob': account_props.primary_endpoints.blob if account_props.primary_endpoints else None
                    }
                })

            except Exception as e:
                logger.error(f"Error processing storage account {account.name}: {e}")
                results.append({
                    'name': account.name,
                    'error': str(e)
                })

        total_cost = sum(r.get('estimated_monthly_cost', 0) for r in results if 'error' not in r)
        total_savings = sum(r.get('potential_monthly_savings', 0) for r in results if 'error' not in r)

        return {
            'subscription_id': sub_id,
            'accounts_analyzed': len(results),
            'total_estimated_monthly_cost': round(total_cost, 2),
            'total_estimated_monthly_cost_formatted': format_cost(total_cost),
            'total_potential_savings': round(total_savings, 2),
            'total_potential_savings_formatted': format_cost(total_savings),
            'storage_accounts': results
        }

    except Exception as e:
        logger.error(f"Error in get_storage_account_usage: {e}", exc_info=True)
        return {"error": str(e)}


async def analyze_blob_tiers(subscription_id: str = None, resource_group: str = None,
                             storage_account_name: str = None) -> dict:
    """
    Analyze blob storage access patterns and recommend tier optimizations

    Args:
        subscription_id: Azure subscription ID (optional)
        resource_group: Resource group name (optional)
        storage_account_name: Storage account name to analyze (optional)

    Returns:
        dict with blob tier recommendations
    """
    try:
        sub_id = subscription_id or azure_clients.subscription_id
        if not sub_id:
            return {"error": "AZURE_SUBSCRIPTION_ID not configured"}

        storage_client = azure_clients.get_storage_client(sub_id)

        # List storage accounts
        if resource_group and storage_account_name:
            accounts = [storage_client.storage_accounts.get_properties(resource_group, storage_account_name)]
        elif resource_group:
            accounts = list(storage_client.storage_accounts.list_by_resource_group(resource_group))
        else:
            accounts = list(storage_client.storage_accounts.list())

        # Filter for blob storage accounts
        blob_accounts = [acc for acc in accounts if acc.kind in ['StorageV2', 'BlobStorage']]

        if not blob_accounts:
            return {"message": "No blob storage accounts found", "accounts": []}

        recommendations = []
        total_potential_savings = 0

        for account in blob_accounts[:5]:  # Limit to 5 accounts
            # General recommendations based on account type
            recommendation = {
                'storage_account': account.name,
                'resource_group': account.id.split('/')[4],
                'current_tier': account.access_tier if hasattr(account, 'access_tier') else 'Hot',
                'recommendations': [
                    {
                        'suggestion': 'Enable lifecycle management to automatically move blobs to Cool/Archive tier',
                        'description': 'Blobs not accessed for 30+ days → Cool tier (50% storage cost savings)',
                        'potential_monthly_savings': '~$50-200 depending on data size',
                        'implementation': 'Use Azure Portal > Storage Account > Lifecycle Management or Azure CLI'
                    },
                    {
                        'suggestion': 'Archive rarely accessed blobs',
                        'description': 'Blobs not accessed for 180+ days → Archive tier (90% storage cost savings)',
                        'potential_monthly_savings': '~$100-500 depending on data size',
                        'implementation': 'Set up lifecycle policies with conditions for last access time'
                    },
                    {
                        'suggestion': 'Review and delete old snapshots',
                        'description': 'Old blob snapshots consume storage and may not be needed',
                        'potential_monthly_savings': '~$20-100 depending on snapshot count',
                        'implementation': 'az storage blob snapshot list and delete unused snapshots'
                    }
                ]
            }

            recommendations.append(recommendation)
            total_potential_savings += 170  # Average of suggested savings

        return {
            'subscription_id': sub_id,
            'blob_accounts_analyzed': len(recommendations),
            'total_potential_monthly_savings': total_potential_savings,
            'total_potential_monthly_savings_formatted': format_cost(total_potential_savings),
            'total_potential_annual_savings': total_potential_savings * 12,
            'total_potential_annual_savings_formatted': format_cost(total_potential_savings * 12),
            'recommendations': recommendations,
            'general_best_practices': [
                'Enable lifecycle management policies for automated tier transitions',
                'Use Cool tier for data accessed less than once per month',
                'Use Archive tier for compliance/backup data rarely accessed',
                'Monitor access patterns with Storage Analytics',
                'Delete unnecessary blob versions and snapshots'
            ]
        }

    except Exception as e:
        logger.error(f"Error in analyze_blob_tiers: {e}", exc_info=True)
        return {"error": str(e)}


def _estimate_storage_cost(sku_name: str, endpoints) -> float:
    """
    Estimate storage account monthly cost based on SKU
    This is a simplified estimation - production should use Azure Retail Prices API
    """
    # Base costs per GB per month
    base_costs = {
        'Premium_LRS': 150,  # Higher base for premium
        'Premium_ZRS': 180,
        'Standard_LRS': 50,
        'Standard_GRS': 100,
        'Standard_RAGRS': 125,
        'Standard_ZRS': 60,
        'Standard_GZRS': 120
    }

    return base_costs.get(sku_name, 50)
