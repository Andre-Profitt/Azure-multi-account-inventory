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
"""Asynchronous Azure Resource Graph collector."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.resourcegraph.aio import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()
UTC = timezone.utc


class AzureResourceGraphCollector:
    """Collect resources across subscriptions using Azure Resource Graph."""

    def __init__(self, config_path: str, credential: DefaultAzureCredential | None = None) -> None:
        self.config_path = config_path
        self.credential = credential or DefaultAzureCredential()
        self.subscriptions: List[str] = []
        self.resource_types: List[str] = []
        self.tag_filters: Dict[str, str] = {}
        self.excluded_regions: List[str] = []
        self.subscription_map: Dict[str, str] = {}
        self._load_config()

    def _load_config(self) -> None:
        with open(self.config_path) as f:
            data = json.load(f)
        subs = data.get("subscriptions", {})
        self.subscription_map = {name: info["subscription_id"] for name, info in subs.items()}
        self.subscriptions = list(self.subscription_map.values())
        self.resource_types = data.get("resource_types", [])
        self.tag_filters = data.get("tag_filters", {})
        self.excluded_regions = data.get("excluded_regions", [])
        logger.info("loaded_config", subscriptions=len(self.subscriptions))

    def _build_query(self) -> str:
        query_parts = ["Resources"]
        if self.resource_types:
            type_list = ",".join([f"'{t}'" for t in self.resource_types])
            query_parts.append(f"| where type in~ ({type_list})")
        for k, v in self.tag_filters.items():
            query_parts.append(f"| where tags['{k}'] == '{v}'")
        if self.excluded_regions:
            regions = ",".join([f"'{r}'" for r in self.excluded_regions])
            query_parts.append(f"| where location !in~ ({regions})")
        query_parts.append("| project id, name, type, location, tags, subscriptionId")
        return " ".join(query_parts)

    @retry(wait=wait_exponential(multiplier=2, min=1, max=32), stop=stop_after_attempt(5))
    async def _execute(self, client: ResourceGraphClient, request: QueryRequest) -> Any:
        logger.debug("executing_query", query=request.query)
        return await client.resources(request)

    async def collect(self) -> List[Dict[str, Any]]:
        query = self._build_query()
        client = ResourceGraphClient(credential=self.credential)
        request = QueryRequest(
            subscriptions=self.subscriptions,
            query=query,
            options={"resultFormat": "objectArray", "top": 1000},
        )
        all_data: List[Dict[str, Any]] = []
        response = await self._execute(client, request)
        all_data.extend(response.data)
        skip = response.skip_token
        # Handle paging using skip tokens
        while skip:
            request.options["skipToken"] = skip
            response = await self._execute(client, request)
            all_data.extend(response.data)
            skip = response.skip_token
        await client.close()
        return [self._normalize(r) for r in all_data]

    def _normalize(self, item: Dict[str, Any]) -> Dict[str, Any]:
        sub_id = item.get("subscriptionId")
        name = next((n for n, sid in self.subscription_map.items() if sid == sub_id), sub_id)
        return {
            "composite_key": f"{sub_id}#{item['type']}#{item['name']}",
            "timestamp": datetime.now(UTC).isoformat(),
            "account_id": sub_id,
            "account_name": name,
            "region": item.get("location"),
            "resource_type": item.get("type"),
            "resource_id": item.get("id"),
            "resource_name": item.get("name"),
            "tags": item.get("tags", {}),
        }


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Azure Resource Graph collector")
    parser.add_argument("--config", required=True, help="Path to azure_subscriptions.json")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(args.log_level.upper()))
    collector = AzureResourceGraphCollector(args.config)
    resources = await collector.collect()
    logger.info("collected", count=len(resources))
    print(json.dumps(resources, indent=2))


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
