import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from collector.enhanced_main import AzureInventoryCollector


class TestAzureInventoryCollector(unittest.TestCase):
    """Unit tests for AzureInventoryCollector"""

    @patch('collector.enhanced_main.DefaultAzureCredential')
    @patch('collector.enhanced_main.ComputeManagementClient')
    def test_collect_virtual_machines(self, mock_compute_client, mock_cred):
        mock_vm = Mock()
        mock_vm.id = 'vm1'
        mock_vm.location = 'eastus'
        mock_vm.hardware_profile.vm_size = 'Standard_B1s'
        mock_vm.storage_profile.os_disk.os_type.value = 'Linux'
        mock_vm.tags = {'env': 'test'}
        mock_compute_client.return_value.virtual_machines.list_all.return_value = [mock_vm]

        collector = AzureInventoryCollector('sub123')
        resources = collector.collect_virtual_machines()

        self.assertEqual(len(resources), 1)
        res = resources[0]
        self.assertEqual(res['resource_type'], 'vm')
        self.assertEqual(res['account_id'], 'sub123')
        self.assertEqual(res['region'], 'eastus')

    @patch('collector.enhanced_main.DefaultAzureCredential')
    @patch('collector.enhanced_main.ComputeManagementClient')
    def test_estimate_network_cost(self, mock_compute_client, mock_cred):
        collector = AzureInventoryCollector('sub123')
        metrics = {'data_processed_gb': 100}
        cost = collector.estimate_network_cost(metrics)
        self.assertEqual(cost, 1.0)

    @patch('collector.enhanced_main.TableServiceClient')
    @patch('collector.enhanced_main.DefaultAzureCredential')
    @patch('collector.enhanced_main.ComputeManagementClient')
    def test_collect_inventory_persists(self, mock_compute_client, mock_cred, mock_table_service):
        mock_vm = Mock()
        mock_vm.id = 'vm1'
        mock_vm.location = 'eastus'
        mock_vm.hardware_profile.vm_size = 'Standard_B1s'
        mock_vm.storage_profile.os_disk.os_type.value = 'Linux'
        mock_vm.tags = {'env': 'test'}
        mock_compute_client.return_value.virtual_machines.list_all.return_value = [mock_vm]

        mock_service = Mock()
        mock_table = Mock()
        mock_table_service.return_value = mock_service
        mock_service.get_table_client.return_value = mock_table

        os.environ['AZURE_TABLE_URL'] = 'https://table.test'
        os.environ['AZURE_TABLE_NAME'] = 'inventory'

        collector = AzureInventoryCollector('sub123')
        resources = collector.collect_inventory()

        mock_table_service.assert_called_with(endpoint='https://table.test', credential=mock_cred.return_value)
        mock_service.get_table_client.assert_called_with('inventory')
        mock_table.upsert_entity.assert_called_once()
        self.assertEqual(len(resources), 1)

    @patch('collector.enhanced_main.DefaultAzureCredential')
    @patch('collector.enhanced_main.SqlManagementClient')
    def test_collect_sql_databases_handles_bad_id(self, mock_sql_client, mock_cred):
        mock_db_good = Mock()
        mock_db_good.id = '/subscriptions/sub123/resourceGroups/rg1/providers/Microsoft.Sql/servers/srv1/databases/db1'
        mock_db_good.location = 'eastus'
        mock_db_good.tags = {'env': 'prod'}

        mock_db_bad = Mock()
        mock_db_bad.id = 'badformat'
        mock_db_bad.location = 'westus'
        mock_db_bad.tags = None

        mock_sql_client.return_value.databases.list_by_subscription.return_value = [
            mock_db_good, mock_db_bad
        ]

        collector = AzureInventoryCollector('sub123')
        resources = collector.collect_sql_databases()

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['attributes']['resource_group'], 'rg1')
        self.assertEqual(resources[1]['attributes']['resource_group'], 'unknown')


if __name__ == '__main__':
    unittest.main()
