import os
import sys
from datetime import datetime, timezone
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from collector.azure_policy_client import AzurePolicyClient

UTC = timezone.utc


@patch('collector.azure_policy_client.PolicyInsightsClient')
@patch('collector.azure_policy_client.TableServiceClient')
def test_fetch_and_save_non_compliant(mock_table_service, mock_policy_client):
    mock_state = Mock()
    mock_state.resource_id = '/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1'
    mock_state.policy_assignment_name = 'assign'
    mock_state.policy_definition_name = 'def'
    mock_state.timestamp = datetime(2023, 1, 1, tzinfo=UTC)

    mock_policy_client.return_value.policy_states.list_query_results_for_subscription.return_value = [mock_state]

    mock_table = Mock()
    mock_table_service.return_value.get_table_client.return_value = mock_table

    client = AzurePolicyClient('sub', 'https://example.table.core.windows.net')
    findings = client.fetch_non_compliant()
    assert len(findings) == 1
    client.save_findings(findings)

    mock_table.upsert_entity.assert_called_once()
