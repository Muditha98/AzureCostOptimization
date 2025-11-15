""" Shared Azure client initialization and helper functions """

import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from azure.identity import DefaultAzureCredential
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.cosmosdb import CosmosDBManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.costmanagement import CostManagementClient

logger = logging.getLogger(__name__)


class AzureClientManager:
    """Centralized Azure client management with singleton pattern"""

    _instance = None
    _clients = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AzureClientManager, cls).__new__(cls)
            cls._instance._initialize_credential()
        return cls._instance

    def _initialize_credential(self):
        """Initialize Azure credential once"""
        self.credential = DefaultAzureCredential(
            exclude_environment_credential=True,
            exclude_managed_identity_credential=True
        )
        self.subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')

        if not self.subscription_id:
            logger.warning("AZURE_SUBSCRIPTION_ID not set in environment")

    def get_compute_client(self, subscription_id: Optional[str] = None) -> ComputeManagementClient:
        """Get or create ComputeManagementClient"""
        sub_id = subscription_id or self.subscription_id
        key = f"compute_{sub_id}"

        if key not in self._clients:
            self._clients[key] = ComputeManagementClient(self.credential, sub_id)
            logger.info(f"Created ComputeManagementClient for subscription {sub_id}")

        return self._clients[key]

    def get_monitor_client(self, subscription_id: Optional[str] = None) -> MonitorManagementClient:
        """Get or create MonitorManagementClient"""
        sub_id = subscription_id or self.subscription_id
        key = f"monitor_{sub_id}"

        if key not in self._clients:
            self._clients[key] = MonitorManagementClient(self.credential, sub_id)
            logger.info(f"Created MonitorManagementClient for subscription {sub_id}")

        return self._clients[key]

    def get_storage_client(self, subscription_id: Optional[str] = None) -> StorageManagementClient:
        """Get or create StorageManagementClient"""
        sub_id = subscription_id or self.subscription_id
        key = f"storage_{sub_id}"

        if key not in self._clients:
            self._clients[key] = StorageManagementClient(self.credential, sub_id)
            logger.info(f"Created StorageManagementClient for subscription {sub_id}")

        return self._clients[key]

    def get_network_client(self, subscription_id: Optional[str] = None) -> NetworkManagementClient:
        """Get or create NetworkManagementClient"""
        sub_id = subscription_id or self.subscription_id
        key = f"network_{sub_id}"

        if key not in self._clients:
            self._clients[key] = NetworkManagementClient(self.credential, sub_id)
            logger.info(f"Created NetworkManagementClient for subscription {sub_id}")

        return self._clients[key]

    def get_sql_client(self, subscription_id: Optional[str] = None) -> SqlManagementClient:
        """Get or create SqlManagementClient"""
        sub_id = subscription_id or self.subscription_id
        key = f"sql_{sub_id}"

        if key not in self._clients:
            self._clients[key] = SqlManagementClient(self.credential, sub_id)
            logger.info(f"Created SqlManagementClient for subscription {sub_id}")

        return self._clients[key]

    def get_cosmosdb_client(self, subscription_id: Optional[str] = None) -> CosmosDBManagementClient:
        """Get or create CosmosDBManagementClient"""
        sub_id = subscription_id or self.subscription_id
        key = f"cosmosdb_{sub_id}"

        if key not in self._clients:
            self._clients[key] = CosmosDBManagementClient(self.credential, sub_id)
            logger.info(f"Created CosmosDBManagementClient for subscription {sub_id}")

        return self._clients[key]

    def get_resource_client(self, subscription_id: Optional[str] = None) -> ResourceManagementClient:
        """Get or create ResourceManagementClient"""
        sub_id = subscription_id or self.subscription_id
        key = f"resource_{sub_id}"

        if key not in self._clients:
            self._clients[key] = ResourceManagementClient(self.credential, sub_id)
            logger.info(f"Created ResourceManagementClient for subscription {sub_id}")

        return self._clients[key]

    def get_cost_client(self) -> CostManagementClient:
        """Get or create CostManagementClient (doesn't require subscription_id)"""
        key = "cost"

        if key not in self._clients:
            self._clients[key] = CostManagementClient(self.credential)
            logger.info("Created CostManagementClient")

        return self._clients[key]


# Helper functions for common operations

def get_time_range(days: int = 7) -> tuple[str, str]:
    """Get ISO formatted time range for Azure queries"""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)
    return start_time.isoformat(), end_time.isoformat()


def calculate_disk_cost(sku: str, size_gb: int) -> float:
    """
    Estimate monthly disk cost based on SKU and size
    Simplified pricing - would use Azure Retail Prices API in production
    """
    pricing = {
        'Premium_LRS': 0.135,  # per GB/month
        'StandardSSD_LRS': 0.075,
        'Standard_LRS': 0.04,
        'Premium_ZRS': 0.169,
        'StandardSSD_ZRS': 0.094
    }
    return pricing.get(sku, 0.04) * size_gb


def calculate_vm_cost(size: str, hours: int = 730) -> float:
    """
    Estimate VM cost per month (730 hours)
    Simplified pricing - would use Azure Retail Prices API in production
    """
    # Sample pricing for common VM sizes (West US 2, pay-as-you-go)
    vm_pricing = {
        'Standard_B1s': 0.0104,  # per hour
        'Standard_B2s': 0.0416,
        'Standard_D2s_v3': 0.096,
        'Standard_D4s_v3': 0.192,
        'Standard_D8s_v3': 0.384,
        'Standard_D16s_v3': 0.768,
        'Standard_E2s_v3': 0.126,
        'Standard_E4s_v3': 0.252,
        'Standard_F2s_v2': 0.085,
        'Standard_F4s_v2': 0.169
    }
    hourly_rate = vm_pricing.get(size, 0.10)  # Default to $0.10/hour if not found
    return hourly_rate * hours


def format_cost(amount: float) -> str:
    """Format cost amount as currency string"""
    return f"${amount:,.2f}"


def get_resource_id(subscription_id: str, resource_group: str,
                   provider: str, resource_type: str, resource_name: str) -> str:
    """Build Azure resource ID"""
    return (f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/"
            f"providers/{provider}/{resource_type}/{resource_name}")


# Singleton instance
azure_clients = AzureClientManager()
