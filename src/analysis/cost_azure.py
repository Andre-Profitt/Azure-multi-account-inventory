# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Collect Azure cost data and store daily deltas in Cosmos DB."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryAggregation,
    QueryDataset,
    QueryDefinition,
    QueryTimePeriod,
)
from azure.cosmos import CosmosClient


def _backoff(func):
    """Simple exponential backoff decorator for API calls."""

    def wrapper(*args, **kwargs):
        delay = 1
        for attempt in range(5):
            try:
                return func(*args, **kwargs)
            except Exception:  # pragma: no cover - network errors only in prod
                if attempt == 4:
                    raise
                time.sleep(delay)
                delay *= 2

    return wrapper


class AzureCostCollector:
    """Fetch daily cost data from Azure Cost Management and store in Cosmos DB."""

    def __init__(self, subscription_id: str, cosmos_conn: str, db_name: str,
                 container_name: str = "cost") -> None:
        self.subscription_id = subscription_id
        self.credential = DefaultAzureCredential()
        self.cost_client = CostManagementClient(self.credential)
        cosmos = CosmosClient.from_connection_string(cosmos_conn)
        self.container = cosmos.get_database_client(db_name).get_container_client(container_name)

    @_backoff
    def _fetch_cost(self, day: datetime.date) -> float:
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        definition = QueryDefinition(
            type="Usage",
            timeframe="Custom",
            time_period=QueryTimePeriod(from_property=start, to=end),
            dataset=QueryDataset(
                granularity="Daily",
                aggregation={
                    "totalCost": QueryAggregation(name="PreTaxCost", function="Sum")
                },
            ),
        )
        result = self.cost_client.query.usage(
            scope=f"/subscriptions/{self.subscription_id}",
            parameters=definition,
        )
        if result.rows:
            row = result.rows[0]
            return float(row[1] if len(row) > 1 else row[0])
        return 0.0

    def _get_last_total(self) -> float:
        query = (
            "SELECT TOP 1 c.total_cost FROM c WHERE c.subscription_id=@sub "
            "ORDER BY c.date DESC"
        )
        items = list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@sub", "value": self.subscription_id}],
                enable_cross_partition_query=True,
            )
        )
        if items:
            return float(items[0]["total_cost"])
        return 0.0

    def update_daily_cost(self, day: Optional[datetime.date] = None) -> dict:
        if day is None:
            day = datetime.utcnow().date() - timedelta(days=1)
        total = self._fetch_cost(day)
        previous = self._get_last_total()
        delta = total - previous
        item = {
            "id": f"{self.subscription_id}_{day.isoformat()}",
            "subscription_id": self.subscription_id,
            "date": day.isoformat(),
            "total_cost": total,
            "delta": delta,
        }
        self.container.upsert_item(item)
        return item


def collect_daily_costs() -> None:
    """Entry point used by the handler."""
    sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
    conn = os.environ.get("AZURE_COSMOS_CONNECTION_STRING")
    db = os.environ.get("AZURE_COSMOS_DB_NAME")
    if not (sub_id and conn and db):
        print("Azure cost collection skipped; configuration missing")
        return
    collector = AzureCostCollector(sub_id, conn, db)
    data = collector.update_daily_cost()
    print(f"Azure cost data recorded: {data}")
