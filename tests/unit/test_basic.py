"""Basic smoke tests for collector and query modules."""

import os
import sys
from importlib import import_module
from unittest.mock import Mock, patch


# Ensure the src directory is on the path like other tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))


def test_collector_and_query_initialization():
    """Import key modules and verify classes can be instantiated."""

    collector_mod = import_module('collector.enhanced_main')
    query_mod = import_module('query.enhanced_inventory_query')

    assert hasattr(collector_mod, 'AWSInventoryCollector')
    assert hasattr(query_mod, 'InventoryQuery')

    with patch('collector.enhanced_main.boto3.resource') as mock_resource:
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table

        collector = collector_mod.AWSInventoryCollector(table_name='test-table')
        assert collector.table is mock_table

    with patch('query.enhanced_inventory_query.boto3.resource') as mock_resource:
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table

        query = query_mod.InventoryQuery(table_name='test-table')
        assert query.table is mock_table
