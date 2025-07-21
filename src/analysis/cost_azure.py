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
"""Cost and usage insights for Azure subscriptions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.cosmos.aio import CosmosClient
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()
UTC = timezone.utc


class AzureCostCollector:
    """Collect daily cost data and store deltas in Cosmos DB."""

    def __init__(self, subscription_id: str, cosmos_url: str, database: str = "inventory", container: str = "cost") -> None:
        self.subscription_id = subscription_id
        self.cosmos_url = cosmos_url
        self.database = database
        self.container = container
        self.credential = DefaultAzureCredential()
        self.cost_client = CostManagementClient(self.credential)
        self.cosmos_client = CosmosClient(cosmos_url, credential=self.credential)

    @retry(wait=wait_exponential(multiplier=2, min=2, max=30), stop=stop_after_attempt(4))
    async def _query_cost(self) -> Dict[str, Any]:
        scope = f"/subscriptions/{self.subscription_id}"
        params = {
            "type": "Usage",
            "dataSet": {"granularity": "Daily"},
            "timeframe": "MonthToDate",
        }
        logger.debug("cost_query", scope=scope)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.cost_client.query.usage(scope, params))

    async def collect_and_store(self) -> List[Dict[str, Any]]:
        result = await self._query_cost()
        rows = result.rows or []
        if len(rows) < 2:
            logger.warning("not_enough_cost_data", rows=len(rows))
            return []
        last, prev = rows[-1], rows[-2]
        cost_column = result.columns.index("PreTaxCost") if "PreTaxCost" in result.columns else -1
        date_column = result.columns.index("UsageDate") if "UsageDate" in result.columns else 0
        if cost_column == -1:
            logger.warning("cost_column_missing")
            return []
        latest_cost = float(last[cost_column])
        previous_cost = float(prev[cost_column])
        delta = latest_cost - previous_cost
        document = {
            "id": f"{self.subscription_id}-{last[date_column]}",
            "subscription_id": self.subscription_id,
            "date": last[date_column],
            "cost": latest_cost,
            "delta": delta,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        db = (await self.cosmos_client.create_database_if_not_exists(self.database))
        container = (await db.create_container_if_not_exists(self.container, partition_key="subscription_id"))
        await container.upsert_item(document)
        logger.info("cost_stored", subscription=self.subscription_id, date=document["date"], delta=delta)
        await self.cosmos_client.close()
        return [document]
