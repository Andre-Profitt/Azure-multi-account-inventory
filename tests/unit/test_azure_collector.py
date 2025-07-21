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


if __name__ == '__main__':
    unittest.main()
