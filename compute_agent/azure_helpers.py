""" Azure API helper functions for Compute Optimization Agent """

import logging
import json
from datetime import datetime, timedelta
from shared import azure_clients, get_time_range, calculate_vm_cost, format_cost

logger = logging.getLogger(__name__)


async def get_vm_metrics(subscription_id: str = None, resource_group: str = None,
                        vm_name: str = None, days: int = 7) -> dict:
    """
    Get CPU, memory, and disk metrics for Azure VMs from Azure Monitor

    Args:
        subscription_id: Azure subscription ID (optional, uses default from env)
        resource_group: Resource group name (optional, all RGs if not specified)
        vm_name: VM name (optional, all VMs if not specified)
        days: Number of days to look back (default 7)

    Returns:
        dict with VM metrics data
    """
    try:
        sub_id = subscription_id or azure_clients.subscription_id
        if not sub_id:
            return {"error": "AZURE_SUBSCRIPTION_ID not configured"}

        compute_client = azure_clients.get_compute_client(sub_id)
        monitor_client = azure_clients.get_monitor_client(sub_id)

        # List VMs
        if resource_group:
            vms = list(compute_client.virtual_machines.list(resource_group))
        else:
            vms = list(compute_client.virtual_machines.list_all())

        # Filter by VM name if provided
        if vm_name:
            vms = [vm for vm in vms if vm.name.lower() == vm_name.lower()]

        if not vms:
            return {"message": "No VMs found", "vms": []}

        results = []
        start_time, end_time = get_time_range(days)

        for vm in vms[:10]:  # Limit to 10 VMs to avoid rate limits
            try:
                # Query metrics for this VM
                metrics_data = monitor_client.metrics.list(
                    vm.id,
                    timespan=f"{start_time}/{end_time}",
                    interval='PT1H',  # 1-hour intervals
                    metricnames='Percentage CPU',
                    aggregation='Average'
                )

                # Process CPU metrics
                cpu_avg = 0
                cpu_max = 0
                data_points = []

                for metric in metrics_data.value:
                    if metric.name.value == 'Percentage CPU':
                        timeseries = metric.timeseries[0] if metric.timeseries else None
                        if timeseries and timeseries.data:
                            values = [d.average for d in timeseries.data if d.average is not None]
                            if values:
                                cpu_avg = sum(values) / len(values)
                                cpu_max = max(values)
                                data_points = values[:24]  # Last 24 hours

                # Calculate cost
                vm_size = vm.hardware_profile.vm_size
                monthly_cost = calculate_vm_cost(vm_size)

                # Determine optimization recommendation
                recommendation = ""
                potential_savings = 0
                if cpu_avg < 10:
                    recommendation = "HIGH PRIORITY: VM is severely underutilized. Consider shutting down or significant downsizing."
                    potential_savings = monthly_cost * 0.75  # 75% savings from major downsize
                elif cpu_avg < 20:
                    recommendation = "MEDIUM PRIORITY: VM is underutilized. Consider downsizing to smaller SKU."
                    potential_savings = monthly_cost * 0.40  # 40% savings from downsize
                elif cpu_avg < 40:
                    recommendation = "LOW PRIORITY: VM has headroom. Monitor and consider downsizing if pattern continues."
                    potential_savings = monthly_cost * 0.25  # 25% potential savings
                else:
                    recommendation = "Optimally sized. No action needed."
                    potential_savings = 0

                vm_data = {
                    'name': vm.name,
                    'resource_group': vm.id.split('/')[4],
                    'location': vm.location,
                    'size': vm_size,
                    'power_state': vm.instance_view.statuses[1].code if vm.instance_view and len(vm.instance_view.statuses) > 1 else 'unknown',
                    'cpu_average_percent': round(cpu_avg, 2),
                    'cpu_max_percent': round(cpu_max, 2),
                    'monthly_cost_usd': monthly_cost,
                    'monthly_cost_formatted': format_cost(monthly_cost),
                    'is_underutilized': cpu_avg < 20,
                    'recommendation': recommendation,
                    'potential_monthly_savings': round(potential_savings, 2),
                    'potential_savings_formatted': format_cost(potential_savings),
                    'data_points_last_24h': data_points
                }

                results.append(vm_data)
                logger.info(f"Processed metrics for VM: {vm.name}, CPU Avg: {cpu_avg:.2f}%")

            except Exception as e:
                logger.error(f"Error getting metrics for VM {vm.name}: {e}")
                results.append({
                    'name': vm.name,
                    'error': str(e)
                })

        # Calculate totals
        total_monthly_cost = sum(r.get('monthly_cost_usd', 0) for r in results if 'error' not in r)
        total_potential_savings = sum(r.get('potential_monthly_savings', 0) for r in results if 'error' not in r)
        underutilized_count = sum(1 for r in results if r.get('is_underutilized', False))

        return {
            'subscription_id': sub_id,
            'time_range_days': days,
            'vms_analyzed': len(results),
            'underutilized_vms': underutilized_count,
            'total_monthly_cost': round(total_monthly_cost, 2),
            'total_monthly_cost_formatted': format_cost(total_monthly_cost),
            'total_potential_savings': round(total_potential_savings, 2),
            'total_potential_savings_formatted': format_cost(total_potential_savings),
            'vms': results
        }

    except Exception as e:
        logger.error(f"Error in get_vm_metrics: {e}", exc_info=True)
        return {"error": str(e)}


async def list_vms(subscription_id: str = None, resource_group: str = None) -> dict:
    """
    List all virtual machines in subscription with basic info

    Args:
        subscription_id: Azure subscription ID (optional)
        resource_group: Resource group filter (optional)

    Returns:
        dict with VM list
    """
    try:
        sub_id = subscription_id or azure_clients.subscription_id
        if not sub_id:
            return {"error": "AZURE_SUBSCRIPTION_ID not configured"}

        compute_client = azure_clients.get_compute_client(sub_id)

        # List VMs
        if resource_group:
            vms = list(compute_client.virtual_machines.list(resource_group))
        else:
            vms = list(compute_client.virtual_machines.list_all())

        results = []
        total_cost = 0

        for vm in vms:
            monthly_cost = calculate_vm_cost(vm.hardware_profile.vm_size)
            total_cost += monthly_cost

            results.append({
                'name': vm.name,
                'resource_group': vm.id.split('/')[4],
                'location': vm.location,
                'size': vm.hardware_profile.vm_size,
                'os_type': vm.storage_profile.os_disk.os_type if vm.storage_profile else 'Unknown',
                'monthly_cost_usd': monthly_cost,
                'monthly_cost_formatted': format_cost(monthly_cost)
            })

        return {
            'subscription_id': sub_id,
            'total_vms': len(results),
            'total_monthly_cost': round(total_cost, 2),
            'total_monthly_cost_formatted': format_cost(total_cost),
            'vms': results
        }

    except Exception as e:
        logger.error(f"Error in list_vms: {e}", exc_info=True)
        return {"error": str(e)}


async def get_vm_right_sizing_recommendations(subscription_id: str = None,
                                               resource_group: str = None,
                                               vm_name: str = None,
                                               cpu_threshold: float = 20.0) -> dict:
    """
    Analyze VM utilization and provide right-sizing recommendations

    Args:
        subscription_id: Azure subscription ID (optional)
        resource_group: Resource group name (optional)
        vm_name: VM name (optional)
        cpu_threshold: CPU utilization threshold below which to recommend downsizing (default 20%)

    Returns:
        dict with right-sizing recommendations
    """
    try:
        # Get VM metrics first
        metrics_data = await get_vm_metrics(subscription_id, resource_group, vm_name, days=7)

        if 'error' in metrics_data:
            return metrics_data

        recommendations = []

        for vm in metrics_data.get('vms', []):
            if 'error' in vm:
                continue

            cpu_avg = vm.get('cpu_average_percent', 0)
            current_size = vm.get('size', '')

            if cpu_avg < cpu_threshold:
                # Simplified recommendation logic - in production, use Azure Advisor API
                recommended_size = _suggest_smaller_size(current_size, cpu_avg)
                current_cost = vm.get('monthly_cost_usd', 0)
                new_cost = calculate_vm_cost(recommended_size)
                savings = current_cost - new_cost

                recommendations.append({
                    'vm_name': vm['name'],
                    'resource_group': vm['resource_group'],
                    'current_size': current_size,
                    'recommended_size': recommended_size,
                    'current_cpu_avg': cpu_avg,
                    'current_monthly_cost': format_cost(current_cost),
                    'recommended_monthly_cost': format_cost(new_cost),
                    'monthly_savings': format_cost(savings),
                    'annual_savings': format_cost(savings * 12),
                    'implementation_steps': [
                        f"1. Test workload on {recommended_size} in dev environment",
                        "2. Schedule maintenance window",
                        f"3. Resize VM: az vm resize --resource-group {vm['resource_group']} --name {vm['name']} --size {recommended_size}",
                        "4. Verify application functionality",
                        "5. Monitor for 24 hours"
                    ],
                    'risk_level': 'Low' if cpu_avg < 10 else 'Medium',
                    'estimated_downtime': '5-10 minutes'
                })

        total_savings = sum(float(r['monthly_savings'].replace('$', '').replace(',', ''))
                           for r in recommendations)

        return {
            'subscription_id': metrics_data.get('subscription_id'),
            'recommendations_count': len(recommendations),
            'total_monthly_savings': format_cost(total_savings),
            'total_annual_savings': format_cost(total_savings * 12),
            'recommendations': recommendations
        }

    except Exception as e:
        logger.error(f"Error in get_vm_right_sizing_recommendations: {e}", exc_info=True)
        return {"error": str(e)}


def _suggest_smaller_size(current_size: str, cpu_avg: float) -> str:
    """Suggest a smaller VM size based on current size and CPU utilization"""

    # Simplified size recommendation mapping
    # In production, use Azure Advisor API or more sophisticated logic
    size_map = {
        'Standard_D16s_v3': 'Standard_D8s_v3',
        'Standard_D8s_v3': 'Standard_D4s_v3',
        'Standard_D4s_v3': 'Standard_D2s_v3',
        'Standard_D2s_v3': 'Standard_B2s',
        'Standard_E16s_v3': 'Standard_E8s_v3',
        'Standard_E8s_v3': 'Standard_E4s_v3',
        'Standard_E4s_v3': 'Standard_E2s_v3',
        'Standard_F16s_v2': 'Standard_F8s_v2',
        'Standard_F8s_v2': 'Standard_F4s_v2',
        'Standard_F4s_v2': 'Standard_F2s_v2',
    }

    # If CPU is very low (<10%), recommend more aggressive downsize
    if cpu_avg < 10 and current_size in size_map:
        smaller = size_map.get(current_size, current_size)
        if smaller in size_map:
            return size_map[smaller]  # Go down 2 sizes
        return smaller

    return size_map.get(current_size, current_size)
