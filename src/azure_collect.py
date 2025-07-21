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
"""Asynchronous Azure inventory collection using Resource Graph."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from azure.core.exceptions import HttpResponseError
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.resourcegraph.aio import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

UTC = UTC


class AzureResourceGraphCollector:
    """Collect resources from multiple Azure subscriptions."""

    def __init__(self, config_path: str = "config/azure_subscriptions.json") -> None:
        self.config_path = config_path
        self.credential = DefaultAzureCredential()
        self.subscriptions: dict[str, str] = {}

    def load_config(self) -> None:
        """Load subscription configuration from a JSON file."""
        with open(self.config_path) as fh:
            data = json.load(fh)
        subs = data.get("subscriptions", {})
        mapping: dict[str, str] = {}
        for name, info in subs.items():
            sub_id = info.get("subscription_id") or info.get("id")
            if sub_id:
                mapping[sub_id] = name
        self.subscriptions = mapping

    def _build_query(
        self,
        resource_types: list[str] | None = None,
        tag_filters: dict[str, str] | None = None,
        excluded_regions: list[str] | None = None,
    ) -> str:
        clauses: list[str] = []
        if resource_types:
            joined = " or ".join([f"type == '{t}'" for t in resource_types])
            clauses.append(f"({joined})")
        if tag_filters:
            for key, val in tag_filters.items():
                clauses.append(f"tags['{key}'] == '{val}'")
        if excluded_regions:
            regions = ",".join([f"'{r}'" for r in excluded_regions])
            clauses.append(f"location !in ({regions})")
        query = "Resources"
        if clauses:
            query += " | where " + " and ".join(clauses)
        return query + " | project id, name, type, location, tags, properties"

    @staticmethod
    def _normalize(sub_id: str, account_name: str, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "composite_key": f"{sub_id}#{item.get('type')}#{item.get('id')}",
            "timestamp": datetime.now(UTC).isoformat(),
            "account_id": sub_id,
            "account_name": account_name,
            "region": item.get("location"),
            "resource_type": item.get("type"),
            "resource_id": item.get("id"),
            "resource_name": item.get("name"),
            "tags": item.get("tags") or {},
            "attributes": item.get("properties") or {},
        }

    @staticmethod
    def _is_throttle(exc: Exception) -> bool:
        return isinstance(exc, HttpResponseError) and exc.status_code in {429, 503}

    @retry(
        reraise=True,
        retry=retry_if_exception(_is_throttle),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def _query(self, client: ResourceGraphClient, request: QueryRequest):
        return await client.resources(request)

    async def collect_inventory(
        self,
        resource_types: list[str] | None = None,
        tag_filters: dict[str, str] | None = None,
        excluded_regions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query Resource Graph and return normalized resources."""
        if not self.subscriptions:
            self.load_config()

        client = ResourceGraphClient(credential=self.credential)
        query_text = self._build_query(resource_types, tag_filters, excluded_regions)
        request = QueryRequest(
            subscriptions=list(self.subscriptions.keys()),
            query=query_text,
            options={"resultFormat": "objectArray"},
        )

        raw_resources: list[dict[str, Any]] = []
        result = await self._query(client, request)
        raw_resources.extend(result.data or [])
        skip = result.skip_token

        while skip:
            request.options["skipToken"] = skip
            result = await self._query(client, request)
            raw_resources.extend(result.data or [])
            skip = result.skip_token

        await client.close()
        await self.credential.close()

        normalized = []
        for item in raw_resources:
            parts = (item.get("id") or "").split("/")
            sub_id = parts[2] if len(parts) > 2 else ""
            account_name = self.subscriptions.get(sub_id, sub_id)
            normalized.append(self._normalize(sub_id, account_name, item))
        return normalized


__all__ = ["AzureResourceGraphCollector"]
