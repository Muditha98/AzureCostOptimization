"""
Azure Network Optimization Helper Functions

This module provides functions to analyze Azure network resources
for cost optimization opportunities.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Any
from shared.azure_clients import AzureClientManager


def list_unattached_public_ips() -> str:
    """
    Find public IP addresses that are not attached to any resource.
    Unattached IPs still incur charges.

    Returns:
        JSON string containing unattached public IP details and cost information.
    """
    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return json.dumps({"error": "AZURE_SUBSCRIPTION_ID not set in environment"})

        client_manager = AzureClientManager()
        network_client = client_manager.get_network_management_client(subscription_id)

        unattached_ips = []
        total_monthly_waste = 0.0

        # Cost per unattached public IP per month (approximate)
        # Standard SKU IPs: ~$4/month, Basic SKU IPs: ~$3.50/month when not attached
        STANDARD_IP_COST = 4.0
        BASIC_IP_COST = 3.5

        # List all public IP addresses
        public_ips = list(network_client.public_ip_addresses.list_all())

        for ip in public_ips:
            # Check if IP is attached to any resource
            is_attached = ip.ip_configuration is not None

            if not is_attached:
                # Parse resource group from IP ID
                resource_parts = ip.id.split('/')
                resource_group = resource_parts[4] if len(resource_parts) > 4 else "Unknown"

                # Determine cost based on SKU
                sku_name = ip.sku.name if ip.sku else "Basic"
                monthly_cost = STANDARD_IP_COST if sku_name == "Standard" else BASIC_IP_COST

                ip_info = {
                    "name": ip.name,
                    "resource_group": resource_group,
                    "location": ip.location,
                    "sku": sku_name,
                    "allocation_method": ip.public_ip_allocation_method,
                    "ip_address": ip.ip_address if ip.ip_address else "Not assigned",
                    "monthly_cost_usd": monthly_cost,
                    "recommendation": f"Delete this unused public IP to save ${monthly_cost:.2f}/month. "
                                      f"Use Azure CLI: az network public-ip delete --name {ip.name} "
                                      f"--resource-group {resource_group}"
                }

                unattached_ips.append(ip_info)
                total_monthly_waste += monthly_cost

        result = {
            "total_unattached_ips": len(unattached_ips),
            "total_monthly_waste_usd": round(total_monthly_waste, 2),
            "annual_savings_potential_usd": round(total_monthly_waste * 12, 2),
            "unattached_ips": unattached_ips
        }

        if len(unattached_ips) == 0:
            result["message"] = "Great! No unattached public IPs found. All IPs are in use."

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to list public IPs: {str(e)}"})


def analyze_load_balancers() -> str:
    """
    Analyze Azure load balancers for optimization opportunities.

    Returns:
        JSON string with load balancer analysis and recommendations.
    """
    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return json.dumps({"error": "AZURE_SUBSCRIPTION_ID not set in environment"})

        client_manager = AzureClientManager()
        network_client = client_manager.get_network_management_client(subscription_id)

        load_balancers_info = []

        # Cost estimates (approximate, varies by region)
        # Basic LB: Free, Standard LB: ~$25/month base + data processing
        STANDARD_LB_BASE_COST = 25.0

        # List all load balancers
        load_balancers = list(network_client.load_balancers.list_all())

        if not load_balancers:
            return json.dumps({
                "message": "No load balancers found in subscription",
                "load_balancers": []
            })

        for lb in load_balancers:
            # Parse resource group from LB ID
            resource_parts = lb.id.split('/')
            resource_group = resource_parts[4] if len(resource_parts) > 4 else "Unknown"

            # Get SKU
            sku_name = lb.sku.name if lb.sku else "Basic"

            # Count backend pools and rules
            backend_pools_count = len(lb.backend_address_pools) if lb.backend_address_pools else 0
            load_balancing_rules_count = len(lb.load_balancing_rules) if lb.load_balancing_rules else 0
            inbound_nat_rules_count = len(lb.inbound_nat_rules) if lb.inbound_nat_rules else 0

            # Check if backend pools have any members
            has_backend_members = False
            if lb.backend_address_pools:
                for pool in lb.backend_address_pools:
                    if pool.backend_ip_configurations and len(pool.backend_ip_configurations) > 0:
                        has_backend_members = True
                        break

            # Calculate estimated cost
            estimated_cost = STANDARD_LB_BASE_COST if sku_name == "Standard" else 0.0

            lb_info = {
                "name": lb.name,
                "resource_group": resource_group,
                "location": lb.location,
                "sku": sku_name,
                "backend_pools_count": backend_pools_count,
                "load_balancing_rules_count": load_balancing_rules_count,
                "inbound_nat_rules_count": inbound_nat_rules_count,
                "has_backend_members": has_backend_members,
                "estimated_monthly_cost_usd": estimated_cost,
            }

            # Recommendations
            recommendations = []

            if not has_backend_members and backend_pools_count > 0:
                recommendations.append(
                    "Load balancer has backend pools but no backend members. "
                    "This load balancer may be unused and can be deleted to save costs."
                )

            if load_balancing_rules_count == 0 and inbound_nat_rules_count == 0:
                recommendations.append(
                    "No load balancing or NAT rules configured. "
                    "This load balancer appears to be unused and can be deleted."
                )

            if sku_name == "Basic":
                recommendations.append(
                    "Using Basic SKU load balancer (free). Consider upgrading to Standard SKU "
                    "for better SLA, availability zones support, and more features."
                )

            if sku_name == "Standard" and not has_backend_members:
                recommendations.append(
                    f"Standard SKU load balancer without backend members costs ~${STANDARD_LB_BASE_COST}/month. "
                    "Delete if no longer needed."
                )

            if not recommendations:
                recommendations.append("Load balancer is properly configured and in use.")

            lb_info["recommendations"] = recommendations
            load_balancers_info.append(lb_info)

        result = {
            "total_load_balancers": len(load_balancers_info),
            "total_estimated_monthly_cost_usd": sum(
                lb.get("estimated_monthly_cost_usd", 0) for lb in load_balancers_info
            ),
            "load_balancers": load_balancers_info
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to analyze load balancers: {str(e)}"})


def analyze_network_interfaces() -> str:
    """
    Analyze network interfaces for optimization opportunities.
    Identifies unused NICs that can be deleted.

    Returns:
        JSON string with network interface analysis.
    """
    try:
        subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return json.dumps({"error": "AZURE_SUBSCRIPTION_ID not set in environment"})

        client_manager = AzureClientManager()
        network_client = client_manager.get_network_management_client(subscription_id)

        nics_info = []
        unused_nics = []

        # List all network interfaces
        network_interfaces = list(network_client.network_interfaces.list_all())

        if not network_interfaces:
            return json.dumps({
                "message": "No network interfaces found in subscription",
                "network_interfaces": []
            })

        for nic in network_interfaces:
            # Parse resource group from NIC ID
            resource_parts = nic.id.split('/')
            resource_group = resource_parts[4] if len(resource_parts) > 4 else "Unknown"

            # Check if NIC is attached to a VM
            is_attached = nic.virtual_machine is not None

            # Check if NIC has public IP
            has_public_ip = False
            public_ip_name = None
            if nic.ip_configurations:
                for ip_config in nic.ip_configurations:
                    if ip_config.public_ip_address:
                        has_public_ip = True
                        public_ip_parts = ip_config.public_ip_address.id.split('/')
                        public_ip_name = public_ip_parts[-1] if public_ip_parts else None
                        break

            nic_info = {
                "name": nic.name,
                "resource_group": resource_group,
                "location": nic.location,
                "is_attached": is_attached,
                "has_public_ip": has_public_ip,
                "public_ip_name": public_ip_name,
                "enable_accelerated_networking": nic.enable_accelerated_networking,
            }

            if not is_attached:
                nic_info["recommendation"] = (
                    f"Network interface is not attached to any VM. "
                    f"Consider deleting to clean up resources. "
                    f"Azure CLI: az network nic delete --name {nic.name} --resource-group {resource_group}"
                )
                unused_nics.append(nic_info)
            else:
                if nic.enable_accelerated_networking:
                    nic_info["recommendation"] = (
                        "Accelerated networking is enabled (good for performance-sensitive workloads)."
                    )
                else:
                    nic_info["recommendation"] = (
                        "Consider enabling accelerated networking for better performance "
                        "(available on most VM sizes at no additional cost)."
                    )

            nics_info.append(nic_info)

        result = {
            "total_network_interfaces": len(nics_info),
            "unused_network_interfaces": len(unused_nics),
            "network_interfaces": nics_info,
            "unused_nics_summary": unused_nics
        }

        if len(unused_nics) == 0:
            result["message"] = "All network interfaces are attached to VMs. No cleanup needed."
        else:
            result["message"] = (
                f"Found {len(unused_nics)} unused network interface(s). "
                "These can be safely deleted to clean up resources."
            )

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to analyze network interfaces: {str(e)}"})
