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
    @patch('collector.enhanced_main.StorageManagementClient')
    def test_collect_storage_accounts(self, mock_storage_client, mock_compute_client, mock_cred):
        mock_sa = Mock()
        mock_sa.id = 'sa1'
        mock_sa.location = 'eastus'
        mock_sa.sku.name = 'Standard_LRS'
        mock_sa.kind = 'StorageV2'
        mock_sa.tags = {'env': 'test'}
        mock_storage_client.return_value.storage_accounts.list.return_value = [mock_sa]

        collector = AzureInventoryCollector('sub123')
        resources = collector.collect_storage_accounts()

        self.assertEqual(len(resources), 1)
        res = resources[0]
        self.assertEqual(res['resource_type'], 'storage_account')
        self.assertEqual(res['region'], 'eastus')

    @patch('collector.enhanced_main.DefaultAzureCredential')
    @patch('collector.enhanced_main.ComputeManagementClient')
    @patch('collector.enhanced_main.SqlManagementClient')
    def test_collect_sql_databases(self, mock_sql_client, mock_compute_client, mock_cred):
        mock_server = Mock()
        mock_server.id = '/subscriptions/sub123/resourceGroups/rg1/providers/Microsoft.Sql/servers/srv1'
        mock_server.name = 'srv1'
        mock_server.location = 'eastus'
        mock_server.tags = {'env': 'test'}
        mock_db = Mock()
        mock_db.id = 'db1'
        mock_db.name = 'db1'
        mock_db.edition = 'Basic'
        mock_db.sku.name = 'Basic'
        mock_sql_client.return_value.servers.list.return_value = [mock_server]
        mock_sql_client.return_value.databases.list_by_server.return_value = [mock_db]

        collector = AzureInventoryCollector('sub123')
        resources = collector.collect_sql_databases()

        self.assertEqual(len(resources), 1)
        res = resources[0]
        self.assertEqual(res['resource_type'], 'sql_database')
        self.assertEqual(res['attributes']['server'], 'srv1')

    @patch('collector.enhanced_main.DefaultAzureCredential')
    @patch('collector.enhanced_main.ComputeManagementClient')
    @patch('collector.enhanced_main.NetworkManagementClient')
    def test_collect_network_resources(self, mock_network_client, mock_compute_client, mock_cred):
        mock_vnet = Mock()
        mock_vnet.id = 'vnet1'
        mock_vnet.location = 'eastus'
        mock_vnet.name = 'vnet1'
        mock_vnet.address_space.address_prefixes = ['10.0.0.0/16']
        mock_vnet.tags = {'env': 'test'}
        mock_nsg = Mock()
        mock_nsg.id = 'nsg1'
        mock_nsg.location = 'eastus'
        mock_nsg.name = 'nsg1'
        mock_nsg.tags = {}
        mock_network_client.return_value.virtual_networks.list_all.return_value = [mock_vnet]
        mock_network_client.return_value.network_security_groups.list_all.return_value = [mock_nsg]

        collector = AzureInventoryCollector('sub123')
        resources = collector.collect_network_resources()

        self.assertEqual(len(resources), 2)
        types = {r['resource_type'] for r in resources}
        self.assertIn('virtual_network', types)
        self.assertIn('network_security_group', types)


if __name__ == '__main__':
    unittest.main()
