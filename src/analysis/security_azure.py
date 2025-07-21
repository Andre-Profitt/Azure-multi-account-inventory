# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Retrieve Azure Policy compliance and store non-compliant resources."""

from __future__ import annotations

from datetime import datetime, timezone
import asyncio
from typing import Any, Dict, List

import structlog
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.resource import PolicyClient
from azure.cosmos.aio import CosmosClient
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()
UTC = timezone.utc


class AzureSecurityCollector:
    """Pull non-compliant resources using Azure Policy."""

    def __init__(self, subscription_id: str, cosmos_url: str, database: str = "inventory", container: str = "security_findings") -> None:
        self.subscription_id = subscription_id
        self.cosmos_url = cosmos_url
        self.database = database
        self.container = container
        self.credential = DefaultAzureCredential()
        self.policy_client = PolicyClient(self.credential)
        self.cosmos_client = CosmosClient(cosmos_url, credential=self.credential)

    @retry(wait=wait_exponential(min=2, max=30), stop=stop_after_attempt(4))
    async def _get_summary(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.policy_client.policy_states.summarize_for_subscription(
                policy_states_resource='latest',
                subscription_id=self.subscription_id,
            ),
        )

    async def collect_and_store(self) -> List[Dict[str, Any]]:
        summary = await self._get_summary()
        non_compliant = summary.summary.non_compliant_resources or 0
        if non_compliant == 0:
            return []
        findings = [
            {
                "id": f"{self.subscription_id}-{datetime.now(UTC).isoformat()}",
                "subscription_id": self.subscription_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "non_compliant_count": non_compliant,
            }
        ]
        db = (await self.cosmos_client.create_database_if_not_exists(self.database))
        container = (await db.create_container_if_not_exists(self.container, partition_key="subscription_id"))
        for item in findings:
            await container.upsert_item(item)
        await self.cosmos_client.close()
        logger.info("security_stored", subscription=self.subscription_id, count=non_compliant)
        return findings
