import os
from datetime import datetime, timezone
from typing import List, Dict

from azure.identity import DefaultAzureCredential
from azure.mgmt.policyinsights import PolicyInsightsClient
from azure.mgmt.policyinsights.models import QueryOptions
from azure.data.tables import TableServiceClient

import structlog

UTC = timezone.utc
logger = structlog.get_logger(__name__)


class AzurePolicyClient:
    """Fetch Azure Policy compliance results and persist non-compliant resources."""

    def __init__(self, subscription_id: str, table_url: str, container_name: str = "security_findings",
                 credential: DefaultAzureCredential | None = None) -> None:
        self.subscription_id = subscription_id
        self.credential = credential or DefaultAzureCredential()
        self.policy_client = PolicyInsightsClient(self.credential, subscription_id)
        service = TableServiceClient(endpoint=table_url, credential=self.credential)
        self.table = service.get_table_client(container_name)

    def fetch_non_compliant(self) -> List[Dict]:
        """Retrieve non-compliant resources for the subscription."""
        options = QueryOptions(filter="complianceState eq 'NonCompliant'")
        states = self.policy_client.policy_states.list_query_results_for_subscription(
            policy_states_resource="latest",
            subscription_id=self.subscription_id,
            query_options=options,
        )
        results = []
        for state in states:
            results.append({
                "resource_id": state.resource_id,
                "policy_assignment": state.policy_assignment_name,
                "policy_definition": state.policy_definition_name,
                "timestamp": state.timestamp.isoformat() if state.timestamp else datetime.now(UTC).isoformat(),
            })
        logger.info("fetched_non_compliant", count=len(results))
        return results

    def save_findings(self, findings: List[Dict]) -> None:
        """Persist findings to the security findings table."""
        if not findings:
            logger.info("no_findings")
            return

        for item in findings:
            entity = {
                "PartitionKey": self.subscription_id,
                "RowKey": item["resource_id"].replace("/", "_"),
                "policy_assignment": item["policy_assignment"],
                "policy_definition": item["policy_definition"],
                "timestamp": item["timestamp"],
            }
            self.table.upsert_entity(entity)
        logger.info("saved_findings", count=len(findings))
